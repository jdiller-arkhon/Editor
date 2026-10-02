"""Local heuristic analysis, deterministic direction and verified CPU rendering."""
from dataclasses import asdict, dataclass, field
import json
import logging
import os
import shutil
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from .config import Settings
from .storytelling import DialogueCue
from .editing import retime_filters, source_offset
from .transitions import BLENDS, LOSSLESS, compose
from .music_sections import choose_section

LOG = logging.getLogger(__name__)


def run(args, cwd=None):
    return subprocess.run(args, check=True, capture_output=True, cwd=cwd)


def probe(path):
    path = Path(path).resolve(strict=True)
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                           '-of', 'json', str(path)]).stdout)
    duration = float(data['format']['duration'])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError(f'Invalid media duration: {path}')
    return {'path': str(path), 'duration': duration, 'streams': data['streams']}


def audio_envelope(path, duration, rate=8000, start=0):
    """Decode bounded mono chunks; memory scales with envelope, not raw audio."""
    envelope = []
    for chunk_start in np.arange(0, duration, 30):
        raw = run(['ffmpeg', '-v', 'error', '-ss', str(start+chunk_start), '-i', str(path),
                   '-t', str(min(30, duration-chunk_start)), '-vn', '-ac', '1', '-ar', str(rate),
                   '-f', 'f32le', 'pipe:1']).stdout
        samples = np.frombuffer(raw, dtype='<f4')
        hop = rate // 20
        for offset in range(0, len(samples), hop):
            block = samples[offset:offset+hop]
            envelope.append(float(np.sqrt(np.mean(block*block))) if len(block) else 0)
    return np.asarray(envelope)


def music_analysis(media, duration, start=0):
    if not any(s['codec_type'] == 'audio' for s in media['streams']):
        raise ValueError('Music input must contain an audio stream')
    energy = audio_envelope(media['path'], duration, start=start)
    if not len(energy):
        raise ValueError('Music contains no decoded samples')
    if float(energy.max()) < 1e-5:
        raise ValueError('Selected music is silent; choose an audible soundtrack')
    # Spectral changes reveal attacks even when overall loudness stays similar.
    rate, hop, window = 8000, 80, 512
    flux, previous = [], None
    for chunk_start in np.arange(0, duration, 30):
        raw = run(['ffmpeg','-v','error','-ss',str(start+chunk_start),'-i',media['path'],
                   '-t',str(min(30,duration-chunk_start)),'-vn','-ac','1','-ar',str(rate),
                   '-f','f32le','pipe:1']).stdout
        samples = np.frombuffer(raw,dtype='<f4')
        for offset in range(0,len(samples),hop):
            block = np.zeros(window)
            segment = samples[offset:offset+window]
            block[:len(segment)] = segment
            spectrum = np.log1p(abs(np.fft.rfft(block*np.hanning(window))))
            flux.append(float(np.maximum(spectrum-previous,0).mean()) if previous is not None else 0)
            previous = spectrum
    onset = np.asarray(flux)
    threshold = max(float(np.quantile(onset,.8)),float(onset.max())*.15)
    peaks = []
    for i in range(1,len(onset)-1):
        t = i*.01
        if onset[i]>threshold and onset[i]>=onset[i-1] and onset[i]>=onset[i+1]:
            if not peaks or t-peaks[-1]>=.25:
                peaks.append(round(t,3))
    return {'onsets':peaks,'energy':energy.tolist(),'hop_seconds':.05,
            'onset_hop_seconds':.01,'source_start':start,
            'method':'positive log spectral flux; attacks, not semantic beats or downbeats'}


def analyze_gameplay(media, settings):
    if not any(s['codec_type'] == 'video' for s in media['streams']):
        raise ValueError('Gameplay input must contain a video stream')
    motion = []
    previous = None
    size = 160*90
    # Chunked decode bounds raw frame memory. Continuity is retained between chunks.
    for start in np.arange(0, media['duration'], 30):
        raw = run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', media['path'],
                   '-t', str(min(30, media['duration']-start)), '-an',
                   '-vf', f'fps={settings.analysis_fps},scale=160:90,format=gray',
                   '-threads', '1', '-f', 'rawvideo', 'pipe:1']).stdout
        count = len(raw)//size
        for frame in np.frombuffer(raw[:count*size], dtype=np.uint8).reshape(count, size):
            current = frame.astype(np.float32)
            motion.append(float(np.mean(abs(current-previous)))/255 if previous is not None else 0)
            previous = current
    if not motion:
        raise ValueError('Gameplay contains no decoded frames')
    scores = np.asarray(motion)
    if any(s['codec_type'] == 'audio' for s in media['streams']):
        audio = audio_envelope(media['path'], media['duration'])
        times = np.arange(len(scores))/settings.analysis_fps
        loudness = np.interp(times, np.arange(len(audio))*.05, audio) if len(audio) else scores*0
        scores = .75*normalize(scores) + .25*normalize(loudness)
    else:
        scores = normalize(scores)
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    selected = []
    for i in order:
        t = i/settings.analysis_fps
        if all(abs(t-c['time']) >= settings.maximum_clip for c in selected):
            selected.append({'source': media['path'], 'time': t, 'score': float(scores[i]),
                             'source_duration': media['duration']})
    return selected


def normalize(values):
    maximum = float(np.max(values))
    return values/maximum if maximum > 0 else values*0


@dataclass(frozen=True)
class Clip:
    source: str
    start: float
    duration: float
    score: float
    speed_profile: str = 'normal'
    anchor_source: float | None = None
    anchor_output: float | None = None


@dataclass(frozen=True)
class Timeline:
    version: int
    music: str
    settings: dict
    clips: list
    dialogue: list = field(default_factory=list)
    transition: str = 'cut'
    transition_duration: float = .2
    faith_message: str = ''
    gameplay_gain: float = 0
    music_gain: float = 1
    normalize_audio: bool = False
    music_start: float = 0

    def validate(self):
        if self.version != 1 or not self.clips:
            raise ValueError('Unsupported or empty timeline')
        Settings(**self.settings)
        if not isinstance(self.faith_message,str) or len(self.faith_message)>140 or '\x00' in self.faith_message:
            raise ValueError('Faith message must be text of at most 140 characters')
        if not np.isfinite(self.music_start) or self.music_start<0:
            raise ValueError("Invalid soundtrack start")
        for gain in (self.gameplay_gain,self.music_gain):
            if not np.isfinite(gain) or not 0<=gain<=2:raise ValueError('Audio gain outside [0, 2]')
        if self.transition not in ('cut', 'fade_black', 'fade_white', 'zoom') + BLENDS:
            raise ValueError('Unsupported transition')
        if not np.isfinite(self.transition_duration) or not 0 < self.transition_duration <= 1:
            raise ValueError('Transition duration must be in (0, 1]')
        for cue in self.dialogue:
            cue.validate(sum(c.duration for c in self.clips))
        for clip in self.clips:
            if clip.speed_profile not in ('normal','impact'):raise ValueError('Unknown speed profile')
            if (clip.anchor_source is None)!=(clip.anchor_output is None):raise ValueError('Incomplete event anchor')
            if clip.anchor_source is not None:
                if not np.isfinite(clip.anchor_source) or not np.isfinite(clip.anchor_output):raise ValueError('Invalid event anchor')
                if not clip.start<=clip.anchor_source<=clip.start+clip.duration or not 0<=clip.anchor_output<=clip.duration:raise ValueError('Event anchor outside clip')
                mapped=clip.start+source_offset(clip.anchor_output,clip.duration,clip.speed_profile)
                if abs(mapped-clip.anchor_source)>1e-5:raise ValueError('Event anchor does not match retiming')
            if not all(np.isfinite(v) for v in (clip.start, clip.duration, clip.score)):
                raise ValueError('Non-finite timeline value')
            if clip.start < 0 or clip.duration <= 0:
                raise ValueError('Invalid clip bounds')

    def save(self, path):
        self.validate()
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        data['clips'] = [Clip(**c) for c in data['clips']]
        data['dialogue'] = [DialogueCue(**c) for c in data.get('dialogue', [])]
        result = cls(**data)
        result.validate()
        return result


def direct(candidates, music, music_path, settings, duration, ordered=False, cinematic=False):
    if not candidates:
        raise ValueError('No candidate moments')
    ranked = candidates if ordered else sorted(candidates, key=lambda c: (-c['score'], c['source'], c['time']))
    clips = []
    used = {c['source']: [] for c in ranked}
    position = 0.0
    while position < duration-1e-6:
        remaining = duration-position
        cuts = [t for t in music['onsets']
                if position+settings.minimum_clip <= t <= position+settings.maximum_clip]
        length = min(remaining, cuts[0]-position if cuts else settings.maximum_clip)
        # Cuts must occupy complete output frames, avoiding cumulative concat drift.
        length=min(remaining,max(1/settings.fps,round(length*settings.fps)/settings.fps))
        profile='impact' if cinematic and len(clips)%3==1 and length>=1 else 'normal'
        interior=[t-position for t in music['onsets'] if position+.25*length<=t<=position+.75*length]
        target=min(interior,key=lambda t:abs(t-length*.5)) if interior else length*.5
        offset=source_offset(target,length,profile)
        choice = None
        shot_pool = ranked
        if cinematic and not ordered:
            # Build toward stronger activity, then give the closing message room.
            phase = position/max(duration,1e-6)
            desired = .4 if phase < .2 else (.95 if phase < .8 else .35)
            last_source = clips[-1].source if clips else None
            shot_pool = sorted(ranked,key=lambda c:(c['source']==last_source,
                                                    abs(c['score']-desired),c['source'],c['time']))
        # Try every genuine candidate before filling an interval beside an old one.
        for fallback in (False, True):
            for candidate in shot_pool:
                if candidate['source_duration']+1e-6 < length:
                    continue
                start = min(max(0, candidate['time']-offset), candidate['source_duration']-length)
                starts = ([0.0] + [b for a,b in used[candidate['source']]]) if fallback else [start]
                if not fallback and abs(start+offset-candidate['time'])>1e-5:
                    continue
                starts.sort(key=lambda value: abs(value-start))
                for proposed in starts:
                    if proposed+length > candidate['source_duration']+1e-6:
                        continue
                    if all(proposed+length <= a+1e-6 or proposed >= b-1e-6
                           for a,b in used[candidate['source']]):
                        choice = (candidate, proposed)
                        break
                if choice is not None:
                    break
            if choice is not None:
                break
        if choice is None:
            # Never silently repeat source footage to fulfill a requested duration.
            break
        candidate,start = choice
        anchored=abs(start+offset-candidate['time'])<=1e-5
        clips.append(Clip(candidate['source'],start,length,candidate['score'] if anchored else 0,profile,
                          candidate['time'] if anchored else None,target if anchored else None))
        used[candidate['source']].append((start, start+length))
        position += length
    if not clips:
        raise ValueError('Source clips are too short for the selected cut length')
    timeline = Timeline(1, music_path, asdict(settings), clips)
    timeline.validate()
    return timeline


def validate_output(path, settings, expected_duration):
    media = probe(path)
    videos = [s for s in media['streams'] if s['codec_type'] == 'video']
    audios = [s for s in media['streams'] if s['codec_type'] == 'audio']
    if not videos or not audios:
        raise ValueError('Export must contain video and audio')
    video = videos[0]
    for stream in (video,audios[0]):
        stream_duration=float(stream.get('duration',0))
        if abs(stream_duration-expected_duration)>max(.25,2/settings.fps):
            raise ValueError(f"{stream['codec_type']} stream duration {stream_duration:.3f}s differs from timeline {expected_duration:.3f}s")
    if (video['width'], video['height']) != (settings.width, settings.height):
        raise ValueError('Export dimensions do not match timeline')
    numerator, denominator = map(int, video['avg_frame_rate'].split('/'))
    if denominator == 0 or abs(numerator/denominator-settings.fps) > .1:
        raise ValueError('Export frame rate does not match timeline')
    if abs(media['duration']-expected_duration) > max(.25, 2/settings.fps):
        raise ValueError('Export duration does not match timeline')
    # Full decode checks actual encoded frames and audio, rather than metadata alone.
    run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:v:0',
         '-map', '0:a:0', '-f', 'null', '-'])
    return {'valid': True, 'duration': media['duration'], 'width': video['width'],
            'height': video['height'], 'fps': numerator/denominator,
            'video_codec': video['codec_name'], 'audio_codec': audios[0]['codec_name'],
            'full_decode': True}


def render(timeline, output):
    timeline.validate()
    settings = Settings(**timeline.settings)
    output = Path(output).resolve()
    if output.suffix.lower() != '.mp4':
        raise ValueError('The initial renderer requires an .mp4 output')
    if output.exists():
        raise FileExistsError(f'Refusing to replace existing output: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    source_quality = []
    for clip in timeline.clips:
        media = probe(clip.source)
        video = next(s for s in media['streams'] if s['codec_type']=='video')
        if video.get('color_transfer') in ('smpte2084','arib-std-b67'):
            raise ValueError('HDR source requires a tone-mapping workflow; this renderer supports SDR')
        source_quality.append(dict(source=clip.source,width=video['width'],height=video['height'],
            delivery_upscaled=settings.width>video['width'] and settings.height>video['height']))
        if clip.start+clip.duration > media['duration']+.01:
            raise ValueError('Timeline exceeds source duration')
    music = probe(timeline.music)
    duration = sum(c.duration for c in timeline.clips)
    if music['duration']+.01 < timeline.music_start+duration:
        raise ValueError('Music is shorter than timeline')
    for cue in timeline.dialogue:
        voice = probe(cue.source)
        if not any(s['codec_type'] == 'audio' for s in voice['streams']):
            raise ValueError('Dialogue input must contain audio')
        if cue.start+cue.duration > voice['duration']+.01:
            raise ValueError('Dialogue exceeds source duration')
    # Encode on the native temporary filesystem: muxers seek when writing MP4 headers.
    with tempfile.TemporaryDirectory(prefix='montage-') as temporary:
        temporary = Path(temporary)
        if timeline.faith_message:
            (temporary/'faith-title.txt').write_text(timeline.faith_message,encoding='utf-8')
        for i,clip in enumerate(timeline.clips):
            LOG.info('Rendering clip %d/%d', i+1, len(timeline.clips))
            transition_filter = ''
            if timeline.transition in ('fade_black','fade_white'):
                color = 'black' if timeline.transition == 'fade_black' else 'white'
                length = min(timeline.transition_duration, clip.duration/2)
                transition_filter = (f',fade=t=in:d={length}:color={color},'
                                     f'fade=t=out:st={clip.duration-length}:d={length}:color={color}')
            title_filter = ''
            if timeline.faith_message and i == len(timeline.clips)-1:
                title_filter = (f',drawtext=textfile=faith-title.txt:expansion=none:fontcolor=white:'
                                f'fontsize={max(18,settings.height//22)}:box=1:boxcolor=black@0.6:'
                                f'boxborderw=12:x=(w-tw)/2:y=h-th-50')
            media=probe(clip.source)
            has_audio=any(s['codec_type']=='audio' for s in media['streams'])
            graph=retime_filters(clip.duration,clip.speed_profile,has_audio)
            video_filter=(f'scale={settings.width}:{settings.height}:force_original_aspect_ratio=decrease:flags=lanczos:out_color_matrix=bt709:out_range=tv,'
                          f'pad={settings.width}:{settings.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,'
                          f'fps={settings.fps},tpad=stop_mode=clone:stop_duration=0.2,trim=duration={clip.duration}')
            if timeline.transition=='zoom':
                frames=clip.duration*settings.fps
                decay=max(1,min(timeline.transition_duration,clip.duration/2)*settings.fps/2)
                video_filter+=(f",zoompan=z='1+0.06*(exp(-on/{decay})+exp(-({frames}-on)/{decay}))':"
                               f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={settings.width}x{settings.height}:fps={settings.fps}")
            graph.append('[vret]'+video_filter+transition_filter+title_filter+'[vout]')
            if has_audio:
                graph.append(f'[aret]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={clip.duration}[aout]')
            else:
                graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={clip.duration}[aout]')
            run(['ffmpeg','-v','error','-ss',str(clip.start),'-i',clip.source,
                 '-filter_complex_threads','1','-filter_complex',';'.join(graph),'-map','[vout]','-map','[aout]',
                 '-t',str(clip.duration)] + LOSSLESS + [str(temporary/f'{i:05d}.mkv')],cwd=temporary)
        pieces = [(temporary/f'{i:05d}.mkv',clip.duration) for i,clip in enumerate(timeline.clips)]
        boundaries = []
        if timeline.transition in BLENDS and len(pieces)>1:
            LOG.info('Compositing %d transition boundaries',len(pieces)-1)
            pieces,boundaries = compose([p for p,d in pieces],[d for p,d in pieces],settings,
                                        timeline.transition,timeline.transition_duration,temporary,run)
        listing = temporary/'clips.txt'
        listing.write_text(''.join(f"file '{path.name}'\nduration {length:.9f}\n" for path,length in pieces))
        pending = temporary/'final.mp4'
        fade = min(1, duration/4)
        inputs = ['ffmpeg', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
                  '-ss',str(timeline.music_start),'-i', timeline.music]
        filters = [f'[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS,'
                   f'afade=t=in:d={fade},afade=t=out:st={duration-fade}:d={fade},volume={timeline.music_gain}[music]']
        filters.append(f'[0:a]volume={timeline.gameplay_gain}[game]')
        labels = ['[music]','[game]']
        voices = []
        for i,cue in enumerate(timeline.dialogue):
            inputs += ['-i', cue.source]
            delay = round(cue.at*1000)
            filters.append(f'[{i+2}:a]atrim=start={cue.start}:duration={cue.duration},'
                           f'asetpts=PTS-STARTPTS,volume={cue.gain},adelay={delay}:all=1[voice{i}]')
            labels.append(f'[voice{i}]')
            voices.append(f'[voice{i}]')
        if voices:
            filters.append(''.join(voices)+f'amix=inputs={len(voices)}:duration=longest:normalize=0,'
                           f'apad,atrim=duration={duration},asplit=2[voice_mix][sidechain]')
            filters.append('[music][sidechain]sidechaincompress=threshold=0.025:ratio=6:attack=15:release=250[bed]')
            labels=['[bed]','[game]','[voice_mix]']
        filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=first:normalize=0[mixed]')
        mastering = ''
        if timeline.normalize_audio:
            # Measure the actual mixed programme, then apply the measured values.
            measure_inputs = inputs.copy()
            measure_inputs[2] = 'info'
            measure = subprocess.run(measure_inputs + ['-filter_complex',';'.join(filters)+
                ';[mixed]loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json[measured]',
                '-map','[measured]','-t',str(duration),'-f','null','-'],
                check=True,capture_output=True)
            stderr = measure.stderr.decode(errors='replace')
            values = json.loads(stderr[stderr.rfind('{'):stderr.rfind('}')+1])
            keys = {'measured_I':'input_i','measured_TP':'input_tp',
                    'measured_LRA':'input_lra','measured_thresh':'input_thresh','offset':'target_offset'}
            if not all(np.isfinite(float(values[key])) for key in keys.values()):
                raise ValueError('Cannot master a silent or invalid audio mix')
            mastering = 'loudnorm=I=-16:TP=-1.5:LRA=11:linear=true:'+':'.join(
                f'{key}={values[value]}' for key,value in keys.items())+','
        filters.append('[mixed]'+mastering+'alimiter=limit=0.95:level=0:latency=1,aresample=48000[audio]')
        crf,preset = {'draft':('23','fast'),'high':('16','slow'),'master':('12','slow')}[settings.quality]
        run(inputs + ['-filter_complex_threads','1','-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[audio]',
                      '-c:v','libx264','-crf',crf,'-preset',preset,'-pix_fmt','yuv420p','-threads','2',
                      '-c:a', 'aac', '-b:a', '320k', '-t', str(duration),
                      '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
                      '-movflags', '+faststart', str(pending)])
        report = validate_output(pending, settings, duration)
        report['audio_mastering'] = 'measured two-pass loudnorm' if timeline.normalize_audio else 'peak limiter'
        report['edit_effects'] = sorted({c.speed_profile for c in timeline.clips})
        report['music_start'] = timeline.music_start
        report['transition'] = timeline.transition
        report['transition_boundaries'] = boundaries
        report['render_quality'] = dict(preset=settings.quality,crf=int(crf),encoder_preset=preset,
                                      intermediates='lossless FFV1 / PCM',audio_bitrate=320000,
                                      sources=source_quality)
        # Publish only after successful validation; hard link refuses concurrent overwrites.
        # Copy sequentially into the destination filesystem before atomic publication.
        # Native temp and the destination may be on different devices.
        stage_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.montage-publish-',suffix='.mp4',
                                             dir=output.parent,delete=False) as stage:
                stage_path = Path(stage.name)
                with pending.open('rb') as source:
                    shutil.copyfileobj(source,stage)
                stage.flush()
                os.fsync(stage.fileno())
            output.hardlink_to(stage_path)
        finally:
            if stage_path is not None:
                stage_path.unlink(missing_ok=True)
    return report


def create_montage(gameplay, music, output, settings, story=None, ai_model=None, brief=None):
    output = Path(output).resolve()
    sidecars = [output.with_suffix('.timeline.json'), output.with_suffix('.analysis.json'),
                output.with_suffix('.validation.json')]
    if output.exists() or any(p.exists() for p in sidecars):
        raise FileExistsError('Output or its project sidecars already exist')
    sources = [probe(p) for p in gameplay]
    if len({s['path'] for s in sources}) != len(sources):
        raise ValueError('Duplicate gameplay inputs')
    song = probe(music)
    duration = min(settings.duration, song['duration'])
    music_start = 0.0
    if story and story.get('auto_music_section'):
        LOG.info('Selecting an energetic section of the chosen soundtrack')
        envelope = audio_envelope(song['path'],song['duration'])
        music_start = choose_section(envelope,song['duration'],duration)
    analysis = music_analysis(song, duration, start=music_start)
    candidates = []
    for source in sources:
        LOG.info('Analyzing %s', source['path'])
        candidates.extend(analyze_gameplay(source, settings))
    ai_plan = None
    if ai_model:
        from .ai_director import OllamaDirector, configure_plan, DEFAULT_BRIEF
        LOG.info('Requesting local Ollama director plan')
        plan,pool = OllamaDirector(ai_model).plan(candidates,brief or DEFAULT_BRIEF)
        candidates,settings = configure_plan(plan,pool,settings)
        ai_plan = {'provider':'ollama','model':ai_model,'plan':plan,
                   'evidence':'motion/audio metadata only; no visual semantic analysis'}
    timeline = direct(candidates, analysis, song['path'], settings, duration, ordered=bool(ai_model),cinematic=bool(story and story.get('edit_profile')=='cinematic'))
    from dataclasses import replace
    timeline = replace(timeline,music_start=music_start)
    if ai_plan:
        from dataclasses import replace
        timeline = replace(timeline,transition=plan['transition'],transition_duration=plan['transition_duration'])
    if story is not None:
        from dataclasses import replace
        timeline = replace(timeline, dialogue=[DialogueCue(**c) for c in story.get('dialogue', [])],
                           transition=story.get('transition', timeline.transition) if not ai_model else timeline.transition,
                           transition_duration=story.get('transition_duration', timeline.transition_duration) if not ai_model else timeline.transition_duration,
                           faith_message=story.get('faith_message',''),gameplay_gain=story.get('gameplay_gain',0),
                           music_gain=story.get('music_gain',1),normalize_audio=story.get('normalize_audio',False))
    report = render(timeline, output)
    timeline.save(sidecars[0])
    sidecars[1].write_text(json.dumps({'music': analysis, 'candidates': candidates, 'ai_director': ai_plan}, indent=2))
    report['ai_director'] = 'ollama' if ai_model else 'heuristic'
    report['requested_duration'] = settings.duration
    report['shortened'] = sum(c.duration for c in timeline.clips) < settings.duration-.01
    sidecars[2].write_text(json.dumps(report, indent=2))
    return report
