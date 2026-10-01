"""Local heuristic analysis, deterministic direction and verified CPU rendering."""
from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from .config import Settings

LOG = logging.getLogger(__name__)


def run(args):
    return subprocess.run(args, check=True, capture_output=True)


def probe(path):
    path = Path(path).resolve(strict=True)
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                           '-of', 'json', str(path)]).stdout)
    duration = float(data['format']['duration'])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError(f'Invalid media duration: {path}')
    return {'path': str(path), 'duration': duration, 'streams': data['streams']}


def audio_envelope(path, duration, rate=8000):
    """Decode bounded mono chunks; memory scales with envelope, not raw audio."""
    envelope = []
    for start in np.arange(0, duration, 30):
        raw = run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(path),
                   '-t', str(min(30, duration-start)), '-vn', '-ac', '1', '-ar', str(rate),
                   '-f', 'f32le', 'pipe:1']).stdout
        samples = np.frombuffer(raw, dtype='<f4')
        hop = rate // 20
        for offset in range(0, len(samples), hop):
            block = samples[offset:offset+hop]
            envelope.append(float(np.sqrt(np.mean(block*block))) if len(block) else 0)
    return np.asarray(envelope)


def music_analysis(media, duration):
    if not any(s['codec_type'] == 'audio' for s in media['streams']):
        raise ValueError('Music input must contain an audio stream')
    energy = audio_envelope(media['path'], duration)
    if not len(energy):
        raise ValueError('Music contains no decoded samples')
    onset = np.maximum(0, np.diff(energy, prepend=energy[0]))
    threshold = max(float(np.quantile(onset, .8)), float(onset.max())*.15)
    peaks = []
    for i in range(1, len(onset)-1):
        t = i*.05
        if onset[i] > threshold and onset[i] >= onset[i-1] and onset[i] >= onset[i+1]:
            if not peaks or t-peaks[-1] >= .25:
                peaks.append(round(t, 3))
    return {'onsets': peaks, 'energy': energy.tolist(), 'hop_seconds': .05,
            'method': 'positive RMS energy change; not a reliable beat tracker'}


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


@dataclass(frozen=True)
class Timeline:
    version: int
    music: str
    settings: dict
    clips: list

    def validate(self):
        if self.version != 1 or not self.clips:
            raise ValueError('Unsupported or empty timeline')
        Settings(**self.settings)
        for clip in self.clips:
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
        result = cls(**data)
        result.validate()
        return result


def direct(candidates, music, music_path, settings, duration):
    if not candidates:
        raise ValueError('No candidate moments')
    ranked = sorted(candidates, key=lambda c: (-c['score'], c['source'], c['time']))
    clips = []
    used = {c['source']: [] for c in ranked}
    position = 0.0
    while position < duration-1e-6:
        remaining = duration-position
        cuts = [t for t in music['onsets']
                if position+settings.minimum_clip <= t <= position+settings.maximum_clip]
        length = min(remaining, cuts[0]-position if cuts else settings.maximum_clip)
        choice = None
        for candidate in ranked:
            if candidate['source_duration']+1e-6 < length:
                continue
            start = min(max(0, candidate['time']-length*.65), candidate['source_duration']-length)
            starts = [start, 0.0] + [b for a,b in used[candidate['source']]]
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
        if choice is None:
            # Never silently repeat source footage to fulfill a requested duration.
            break
        candidate,start = choice
        clips.append(Clip(candidate['source'], start, length, candidate['score']))
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
    for clip in timeline.clips:
        media = probe(clip.source)
        if clip.start+clip.duration > media['duration']+.01:
            raise ValueError('Timeline exceeds source duration')
    music = probe(timeline.music)
    duration = sum(c.duration for c in timeline.clips)
    if music['duration']+.01 < duration:
        raise ValueError('Music is shorter than timeline')
    with tempfile.TemporaryDirectory(prefix='montage-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        for i,clip in enumerate(timeline.clips):
            LOG.info('Rendering clip %d/%d', i+1, len(timeline.clips))
            run(['ffmpeg', '-v', 'error', '-i', clip.source, '-ss', str(clip.start),
                 '-t', str(clip.duration), '-an', '-vf',
                 f'scale={settings.width}:{settings.height}:force_original_aspect_ratio=decrease,'
                 f'pad={settings.width}:{settings.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={settings.fps}',
                 '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                 '-threads', '2', str(temporary/f'{i:05d}.mp4')])
        listing = temporary/'clips.txt'
        listing.write_text(''.join(f"file '{i:05d}.mp4'\n" for i in range(len(timeline.clips))))
        pending = temporary/'final.mp4'
        fade = min(1, duration/4)
        run(['ffmpeg', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
             '-i', timeline.music, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
             '-af', f'afade=t=in:d={fade},afade=t=out:st={duration-fade}:d={fade}',
             '-c:a', 'aac', '-b:a', '192k', '-t', str(duration), '-movflags', '+faststart', str(pending)])
        report = validate_output(pending, settings, duration)
        # Publish only after successful validation; hard link refuses concurrent overwrites.
        output.hardlink_to(pending)
    return report


def create_montage(gameplay, music, output, settings):
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
    analysis = music_analysis(song, duration)
    candidates = []
    for source in sources:
        LOG.info('Analyzing %s', source['path'])
        candidates.extend(analyze_gameplay(source, settings))
    timeline = direct(candidates, analysis, song['path'], settings, duration)
    report = render(timeline, output)
    timeline.save(sidecars[0])
    sidecars[1].write_text(json.dumps({'music': analysis, 'candidates': candidates}, indent=2))
    report['requested_duration'] = settings.duration
    report['shortened'] = sum(c.duration for c in timeline.clips) < settings.duration-.01
    sidecars[2].write_text(json.dumps(report, indent=2))
    return report
