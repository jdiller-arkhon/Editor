"""Local heuristic analysis, deterministic direction and verified CPU rendering."""
from dataclasses import asdict, dataclass, field, replace
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
from .editing import PROFILES, retime_filters, source_offset
from .transitions import BLENDS, EFFECTS, LOSSLESS, compose
from .music_sections import choose_section
from . import screen_analysis as screens
from . import craft
from . import jobs
from .rhythm import alignment_report, beat_grid, boundary_styles, excerpt_grid, plan_cuts, usable as rhythm_usable

LOG = logging.getLogger(__name__)


def run(args, cwd=None):
    return jobs.run(args, cwd=cwd)


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


def music_analysis(media, duration, start=0, override=None):
    if not any(s['codec_type'] == 'audio' for s in media['streams']):
        raise ValueError('Music input must contain an audio stream')
    energy = audio_envelope(media['path'], duration, start=start)
    if not len(energy):
        raise ValueError('Music contains no decoded samples')
    if float(energy.max()) < 1e-5:
        raise ValueError('Selected music is silent; choose an audible soundtrack')
    # Spectral changes reveal attacks even when overall loudness stays similar.
    rate, hop, window = 8000, 80, 512
    # A Hann-windowed attack produces its largest flux when centred in the window.
    latency = window/2/rate+hop/rate
    flux, low_flux, bass, timbre, previous = [], [], [], [], None
    # Twelve log-spaced bands (~60 Hz-4 kHz) describe timbre for downbeat novelty.
    edges = np.unique(np.round(np.geomspace(4, window//2, 13)).astype(int))
    for chunk_start in np.arange(0, duration, 30):
        raw = run(['ffmpeg','-v','error','-ss',str(start+chunk_start),'-i',media['path'],
                   '-t',str(min(30,duration-chunk_start)),'-vn','-ac','1','-ar',str(rate),
                   '-f','f32le','pipe:1']).stdout
        samples = np.frombuffer(raw,dtype='<f4')
        for offset in range(0,len(samples),hop):
            block = np.zeros(window)
            segment = samples[offset:offset+window]
            block[:len(segment)] = segment
            magnitude = abs(np.fft.rfft(block*np.hanning(window)))
            spectrum = np.log1p(magnitude)
            bass.append(float(np.mean(magnitude[1:10]**2)))   # below ~150 Hz: kick and bass
            timbre.append([float(spectrum[a:b].mean()) for a, b in zip(edges[:-1], edges[1:])])
            rise = np.maximum(spectrum-previous,0) if previous is not None else spectrum*0
            flux.append(float(rise.mean()))
            # Bins below ~200 Hz carry kick/bass accents used for downbeat phase.
            low_flux.append(float(rise[1:14].mean()))
            previous = spectrum
    onset = np.asarray(flux)
    threshold = max(float(np.quantile(onset,.8)),float(onset.max())*.15)
    peaks = []
    for i in range(1,len(onset)-1):
        t = i*.01+latency
        if onset[i]>threshold and onset[i]>=onset[i-1] and onset[i]>=onset[i+1]:
            if not peaks or t-peaks[-1]>=.25:
                peaks.append(round(t,3))
    bass = np.asarray(bass)
    if override:
        from .rhythm import manual_grid
        grid = manual_grid(override['bpm'], float(override.get('first_downbeat', 0))-start, duration,
                           energy, bass=bass, bass_hop=.01)
    else:
        grid = beat_grid(onset,np.asarray(low_flux),energy,latency=latency,bass=bass,timbre=np.asarray(timbre))
    result = {'onsets':peaks,'energy':energy.tolist(),'hop_seconds':.05,
              'onset_hop_seconds':.01,'onset_latency_seconds':latency,'source_start':start,
              'method':'positive log spectral flux; attacks, not semantic beats or downbeats',
              'tempo_bpm':grid['tempo_bpm'],'beats':grid['beats'],'downbeats':grid['downbeats'],
              'bars':grid['bars'],'phrases':grid['phrases'],'beat_confidence':grid['confidence'],
              'beat_evidence':{k:grid.get(k) for k in ('periodicity','beat_alignment','steadiness',
                               'downbeat_confidence','method')}}
    result['cut_mode'] = ('beats (manual grid)' if override else 'beats') if rhythm_usable(result) else 'attacks'
    return result


def analyze_gameplay(media, settings, report=None):
    """Activity candidates plus excluded non-gameplay spans (HUD absent: deaths, menus).

    Scores combine frame motion, gameplay loudness and broadband audio transients
    (gunshots/explosions); they measure activity, not semantic events.
    """
    if not any(s['codec_type'] == 'video' for s in media['streams']):
        raise ValueError('Gameplay input must contain a video stream')
    mask = screens.learn_hud_mask(media['path'], media['duration'])
    motion, hud = [], []
    previous = None
    W, H = screens.WIDTH, screens.HEIGHT
    # Chunked decode bounds raw frame memory. Continuity is retained between chunks.
    for start in np.arange(0, media['duration'], 30):
        raw = run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', media['path'],
                   '-t', str(min(30, media['duration']-start)), '-an',
                   '-vf', f'fps={settings.analysis_fps},scale={W}:{H},format=gray',
                   '-threads', '1', '-f', 'rawvideo', 'pipe:1']).stdout
        count = len(raw)//(W*H)
        for frame in np.frombuffer(raw[:count*W*H], dtype=np.uint8).reshape(count, H, W):
            full = frame.astype(np.float32)
            current = full.reshape(H//2, 2, W//2, 2).mean(axis=(1, 3))
            motion.append(float(np.mean(abs(current-previous)))/255 if previous is not None else 0)
            previous = current
            if mask is not None:
                hud.append(screens.presence(full, mask))
    if not motion:
        raise ValueError('Gameplay contains no decoded frames')
    scores = np.asarray(motion)
    times = np.arange(len(scores))/settings.analysis_fps
    if any(s['codec_type'] == 'audio' for s in media['streams']):
        audio = audio_envelope(media['path'], media['duration'])
        loudness = np.interp(times, np.arange(len(audio))*.05, audio) if len(audio) else scores*0
        flux, hop = screens.transients(media['path'], media['duration'])
        radius = max(1, int(round(.25/hop)))
        impact = np.array([flux[max(0, int(t/hop)-radius):int(t/hop)+radius+1].max()
                           if int(t/hop) < len(flux) else 0.0 for t in times])
        scores = .55*normalize(scores) + .2*normalize(loudness) + .25*impact
    else:
        scores = normalize(scores)
    excluded = []
    if mask is not None and hud:
        relative = np.asarray(hud)/max(float(np.median(hud)), 1e-6)
        scores = scores*np.array([screens.hud_factor(r) for r in relative])
        for a, b in screens.low_spans(times, relative):
            excluded.append({'source': media['path'], 'time': (a+b)/2, 'score': 0.0, 'exclude': True,
                             'span': [max(0.0, a-.5), min(media['duration'], b+.5)],
                             'reason': 'HUD absent (death, scoreboard, menu or loading screen)',
                             'source_duration': media['duration']})
    if report is not None:
        report[media['path']] = dict(hud_mask_pixels=int(mask.sum()) if mask is not None else 0,
                                     excluded_spans=[e['span'] for e in excluded])
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    selected = []
    for i in order:
        t = i/settings.analysis_fps
        if scores[i] <= 0:
            break
        if any(e['span'][0] <= t <= e['span'][1] for e in excluded):
            continue
        if all(abs(t-c['time']) >= settings.maximum_clip for c in selected):
            selected.append({'source': media['path'], 'time': t, 'score': float(scores[i]),
                             'source_duration': media['duration']})
    return selected + excluded


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
    # Output-relative beat accents: a short punch-in zoom with a decaying shake.
    accents: list = field(default_factory=list)


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
    # Per-cut transition overrides ('cut' or an EFFECTS name); empty applies ``transition``.
    boundary_transitions: list = field(default_factory=list)
    # Finishing (defaults keep older projects rendering exactly as before).
    interpolation: str = 'none'
    look: str = 'none'
    motion_blur: bool = False
    reframe: str = 'fit'
    sfx: str = 'none'

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
        if (self.interpolation not in craft.INTERPOLATION or self.look not in craft.LOOKS or
                not isinstance(self.motion_blur, bool) or self.reframe not in craft.REFRAME or
                self.sfx not in craft.SFX):
            raise ValueError('Unsupported finishing option')
        if self.boundary_transitions:
            if len(self.boundary_transitions)!=len(self.clips)-1 or not all(
                    b=='cut' or b in EFFECTS for b in self.boundary_transitions):
                raise ValueError('Invalid per-cut transitions')
            if self.transition not in BLENDS:
                raise ValueError('Per-cut transitions require a composited transition style')
        for cue in self.dialogue:
            cue.validate(sum(c.duration for c in self.clips))
        for clip in self.clips:
            if clip.speed_profile not in PROFILES:raise ValueError('Unknown speed profile')
            if (clip.anchor_source is None)!=(clip.anchor_output is None):raise ValueError('Incomplete event anchor')
            if clip.anchor_source is not None:
                if not np.isfinite(clip.anchor_source) or not np.isfinite(clip.anchor_output):raise ValueError('Invalid event anchor')
                if not clip.start<=clip.anchor_source<=clip.start+clip.duration or not 0<=clip.anchor_output<=clip.duration:raise ValueError('Event anchor outside clip')
                mapped=clip.start+source_offset(clip.anchor_output,clip.duration,clip.speed_profile)
                if abs(mapped-clip.anchor_source)>1e-5:raise ValueError('Event anchor does not match retiming')
            if len(clip.accents)>32 or not all(isinstance(a,(int,float)) and np.isfinite(a) and
                                               0<a<clip.duration for a in clip.accents):
                raise ValueError('Beat accents must lie inside the clip')
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


def _attack_segments(music, settings, duration, cinematic):
    """Original attack-driven pacing: cut on the first attack after the minimum length."""
    segments, position = [], 0.0
    while position < duration-1e-6:
        remaining = duration-position
        cuts = [t for t in music['onsets']
                if position+settings.minimum_clip <= t <= position+settings.maximum_clip]
        length = min(remaining, cuts[0]-position if cuts else settings.maximum_clip)
        # Cuts must occupy complete output frames, avoiding cumulative concat drift.
        length=min(remaining,max(1/settings.fps,round(length*settings.fps)/settings.fps))
        profile='impact' if cinematic and len(segments)%3==1 and length>=1 else 'normal'
        interior=[t-position for t in music['onsets'] if position+.25*length<=t<=position+.75*length]
        target=min(interior,key=lambda t:abs(t-length*.5)) if interior else length*.5
        phase = position/max(duration,1e-6)
        desired = .4 if phase < .2 else (.95 if phase < .8 else .35)
        segments.append((length,profile,target,desired,[]))
        position += length
    return segments


def _beat_segments(music, settings, duration, cinematic):
    """Beat-grid pacing: shot length follows song energy; impacts land on lifts/phrases."""
    segments, previous_impact, building = [], False, False
    plan = plan_cuts(music, settings, duration)
    if not plan:
        # The beat grid cannot satisfy the clip-length bounds; keep attack pacing.
        music['cut_mode'] = 'attacks (beat path infeasible for clip bounds)'
        return _attack_segments(music, settings, duration, cinematic)
    for length, tags in plan:
        starts = tags['starts_phrase']
        if 'build' in starts:
            building = True
        if 'drop' in starts:
            building = False
        lifted = 'rise' in starts or 'drop' in starts or ('grid' in starts and tags['energy'] >= .5)
        profile = 'ramp' if (cinematic and lifted and not previous_impact and length >= 1) else 'normal'
        previous_impact = profile == 'ramp'
        if profile == 'ramp':
            # The ramp is slowest at mid-shot: put the moment there, not on an off-centre beat.
            tags = dict(tags, anchor=length/2)
        # Punch in on interior downbeats of loud, real-time shots; the ramp carries its own feel.
        accents = []
        if cinematic and profile == 'normal' and building:
            # Build-up into a drop: punch on every beat to wind up the tension.
            accents = [round(t,4) for t in tags['interior_beats'] if .2 <= t <= length-.2][:6]
        elif cinematic and profile == 'normal' and tags['energy'] >= .6:
            # Interior downbeats; a one-bar shot punches on the mid-bar (backbeat) beat instead.
            accents = [t for t in tags['interior_downbeats'] if .25 <= t <= length-.25]
            middle = [t for t in tags['interior_beats'] if .25 <= t <= length-.25]
            if not accents and middle:
                accents = [min(middle, key=lambda t: abs(t-length/2))]
            accents = [round(t,4) for t in accents]
        phase = tags['start']/max(duration,1e-6)
        # Match gameplay activity to musical intensity; leave the ending calmer for the title.
        desired = .35 if phase >= .85 else .3+.65*tags['energy']
        if 'drop' in starts:
            desired = 1.05   # the drop gets the strongest moment (hero placement ranks by this)
        segments.append((length,profile,tags['anchor'],desired,accents))
    return segments


def direct(candidates, music, music_path, settings, duration, ordered=False, cinematic=False):
    if not candidates:
        raise ValueError('No candidate moments')
    # Footage a reviewer marked unusable (menus, loading screens) is reserved up front so
    # neither anchored shots nor fallback fills can cover it.
    excluded = [c for c in candidates if c.get('exclude')]
    candidates = [c for c in candidates if not c.get('exclude')]
    if not candidates:
        raise ValueError('No usable candidate moments')
    ranked = candidates if ordered else sorted(candidates, key=lambda c: (-c['score'], c['source'], c['time']))
    planner = _beat_segments if rhythm_usable(music) else _attack_segments
    # Recorded in the analysis sidecar: the pacing actually used for this timeline.
    if planner is _attack_segments or not str(music.get('cut_mode', '')).startswith('beats'):
        music['cut_mode'] = 'beats' if planner is _beat_segments else 'attacks'
    segments = planner(music, settings, duration, cinematic)
    # Hero placement: the strongest moments are reserved for the most intense music
    # (the drop/climax) so they always make the cut, instead of losing to energy matching.
    heroes = {}
    if cinematic and not ordered and len(segments) >= 3:
        count = min(3, len(segments)//3)
        best = sorted(ranked, key=lambda c: (-c['score'], c['source'], c['time']))[:count]
        intense = sorted(range(len(segments)), key=lambda i: (-segments[i][3], i))
        for index, candidate in zip(sorted(intense[:count]), sorted(best, key=lambda c: c['score'])):
            heroes[index] = candidate
    reserved = {id(c) for c in heroes.values()}
    clips = []
    used = {c['source']: [] for c in ranked+excluded}
    for c in excluded:
        a, b = c.get('span') or (c['time']-1, c['time']+1)
        used[c['source']].append((max(0.0, a), min(c['source_duration'], b)))
    for index,(length,profile,target,desired,accents) in enumerate(segments):
        offset=source_offset(target,length,profile)
        choice = None
        shot_pool = ranked
        if cinematic and not ordered:
            # Build toward stronger activity, then give the closing message room.
            last_source = clips[-1].source if clips else None
            shot_pool = sorted((c for c in ranked if id(c) not in reserved),
                               key=lambda c:(c['source']==last_source,
                                             abs(c['score']-desired),c.get('story_rank',1e9),
                                             c['source'],c['time']))
            if index in heroes:
                shot_pool = [heroes[index]]+shot_pool
                reserved.discard(id(heroes[index]))
        # Try every genuine candidate before filling an interval beside an old one.
        for fallback in (False, True):
            for candidate in shot_pool:
                if candidate['source_duration']+1e-6 < length:
                    continue
                start = min(max(0, candidate['time']-offset), candidate['source_duration']-length)
                starts = ([0.0] + [b for a,b in used[candidate['source']]]) if fallback else [start]
                if not fallback and abs(start+offset-candidate['time'])>1e-5 and \
                        not start+.1*length <= candidate['time'] <= start+.9*length:
                    # Exact musical anchoring is impossible at the source edge; still use the
                    # moment if it stays well inside the shot rather than skipping to filler.
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
        contained=start<=candidate['time']<=start+length
        clips.append(Clip(candidate['source'],start,length,candidate['score'] if contained else 0,profile,
                          candidate['time'] if anchored else None,target if anchored else None,accents))
        used[candidate['source']].append((start, start+length))
    if not clips:
        raise ValueError('Source clips are too short for the selected cut length')
    timeline = Timeline(1, music_path, asdict(settings), clips)
    timeline.validate()
    return timeline


def _place(slot, moment):
    """Footage for ``slot`` (a Clip) centred on ``moment`` with the slot's musical timing."""
    target = slot.anchor_output if slot.anchor_output is not None else slot.duration/2
    offset = source_offset(target, slot.duration, slot.speed_profile)
    if moment['source_duration']+1e-6 < slot.duration:
        return None, 'source too short for this shot'
    start = min(max(0.0, moment['time']-offset), moment['source_duration']-slot.duration)
    if not start+.1*slot.duration <= moment['time'] <= start+.9*slot.duration:
        return None, 'moment would fall outside the shot'
    anchored = abs(start+offset-moment['time']) <= 1e-5
    return Clip(moment['source'], start, slot.duration, moment.get('score', slot.score), slot.speed_profile,
                moment['time'] if anchored else None, target if anchored else None, list(slot.accents)), None


def _conflict(clips, index, clip, blocked):
    if any(o.source == clip.source and clip.start < o.start+o.duration-1e-6 and o.start < clip.start+clip.duration-1e-6
           for j, o in enumerate(clips) if j != index):
        return 'would reuse footage already in the cut'
    if any(src == clip.source and clip.start < b and a < clip.start+clip.duration for src, a, b in blocked):
        return 'covers a non-gameplay span'
    return None


def swap_shots(timeline, swaps, excluded=()):
    """Replace shots' footage with alternate moments, keeping each shot's musical timing.

    ``swaps`` is [(shot index, candidate)]. A swap is rejected (and reported) when the moment
    cannot sit inside the shot, the source is too short, or it would reuse footage or cover
    an excluded span. Returns (timeline, applied, rejected).
    """
    clips = list(timeline.clips)
    applied, rejected = [], []
    blocked = [(c['source'], *(c.get('span') or (c['time']-1, c['time']+1))) for c in excluded]
    for index, candidate in swaps:
        clip, reason = _place(clips[index], candidate)
        reason = reason or _conflict(clips, index, clip, blocked)
        if reason:
            rejected.append(dict(shot=index+1, reason=reason)); continue
        clips[index] = clip
        applied.append(dict(shot=index+1, source_time=round(candidate['time'], 3)))
    result = replace(timeline, clips=clips)
    result.validate()
    return result, applied, rejected


def shot_moment(clip):
    """The source instant a shot is built around (its anchor, else its middle)."""
    if clip.anchor_source is not None:
        return clip.anchor_source
    return clip.start+source_offset(clip.duration/2, clip.duration, clip.speed_profile)


def exchange_shots(timeline, first, second, durations=None):
    """Swap the footage of two shots; each keeps its slot's timing. Raises if it cannot fit."""
    clips = list(timeline.clips)
    durations = durations or {}

    def moment(clip):
        length = durations.get(clip.source) or probe(clip.source)['duration']
        return dict(source=clip.source, time=shot_moment(clip), score=clip.score, source_duration=length)
    a, reason_a = _place(clips[first], moment(clips[second]))
    b, reason_b = _place(clips[second], moment(clips[first]))
    if reason_a or reason_b:
        raise ValueError(f'Cannot exchange these shots: {reason_a or reason_b}')
    clips[first], clips[second] = a, b
    for index in (first, second):
        reason = _conflict(clips, index, clips[index], [])
        if reason:
            raise ValueError(f'Cannot exchange these shots: {reason}')
    result = replace(timeline, clips=clips)
    result.validate()
    return result


def retarget(timeline, settings, **finishing):
    """Same edit at another resolution/quality (e.g. final render of a draft preview).

    Shot timing is frame-quantised, so the frame rate must not change.
    """
    if settings.fps != timeline.settings['fps']:
        raise ValueError('A preview can only be finalised at the same frame rate')
    result = replace(timeline, settings=asdict(settings), **finishing)
    result.validate()
    return result


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


def accent_filter(accents, settings):
    """Punch-in zoom (+7%) and a small decaying shake starting on each accent time.

    ``on`` is the output frame index; each pulse decays with a 120 ms time constant over 0.6 s.
    """
    fps = settings.fps
    # Each pulse ends exactly at zero after 0.6 s: zoompan is only an identity at zoom == 1.
    pulse = '+'.join(f'between(on/{fps}-{a:.4f},0,0.6)*(exp(-(on/{fps}-{a:.4f})/0.12)-exp(-5))/(1-exp(-5))'
                     for a in accents)
    zoom = f'1+0.07*min(1,{pulse})'
    shake = f'0.012*iw*min(1,{pulse})*sin(on*2.1)'
    return (f",zoompan=z='{zoom}':x='max(0,min(iw-iw/zoom,iw/2-iw/zoom/2+{shake}))':"
            f"y='max(0,min(ih-ih/zoom,ih/2-ih/zoom/2+{shake.replace('iw','ih').replace('2.1','1.7')}))':"
            f"d=1:s={settings.width}x{settings.height}:fps={fps}")


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
            jobs.report(.75*i/len(timeline.clips), f'Rendering shot {i+1} of {len(timeline.clips)}')
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
            stream=next(s for s in media['streams'] if s['codec_type']=='video')
            numerator,denominator=(stream.get('avg_frame_rate') or stream.get('r_frame_rate') or '30/1').split('/')
            source_fps=float(numerator)/float(denominator or 1) if float(denominator or 1) else 30.0
            before=[]
            if timeline.reframe=='follow' and settings.width/settings.height < .8*stream['width']/stream['height']:
                crop_width=max(2,round(stream['height']*settings.width/settings.height/2)*2)
                before.append(craft.follow_crop(craft.follow_track(clip.source,clip.start,clip.duration),crop_width))
            if clip.speed_profile!='normal':
                before.append(craft.interpolation_filter(timeline.interpolation,source_fps,settings.fps,
                                                         settings.width,settings.height))
            chain=','.join(f for f in before if f)
            if chain:
                graph=[f'[0:v]{chain}[src]']+[g.replace('[0:v]','[src]') for g in graph]
            look=craft.LOOKS[timeline.look]
            blur=craft.motion_blur_filter() if timeline.motion_blur and clip.speed_profile!='normal' else ''
            video_filter=(f'scale={settings.width}:{settings.height}:force_original_aspect_ratio=decrease:flags=lanczos:out_color_matrix=bt709:out_range=tv,'
                          f'pad={settings.width}:{settings.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,'
                          +(look+',' if look else '')+
                          f'fps={settings.fps},'+(blur+',' if blur else '')+
                          f'tpad=stop_mode=clone:stop_duration=0.2,trim=duration={clip.duration}')
            if timeline.transition=='zoom':
                frames=clip.duration*settings.fps
                decay=max(1,min(timeline.transition_duration,clip.duration/2)*settings.fps/2)
                video_filter+=(f",zoompan=z='1+0.06*(exp(-on/{decay})+exp(-({frames}-on)/{decay}))':"
                               f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={settings.width}x{settings.height}:fps={settings.fps}")
            if clip.accents:
                video_filter+=accent_filter(clip.accents,settings)
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
            jobs.report(.75,'Compositing transitions')
            pieces,boundaries = compose([p for p,d in pieces],[d for p,d in pieces],settings,
                                        timeline.transition,timeline.transition_duration,temporary,run,
                                        timeline.boundary_transitions or None)
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
        if timeline.sfx=='swish' and boundaries:
            extra,sfx_filters,sfx_labels=craft.swish_inputs(boundaries,2+len(timeline.dialogue))
            inputs+=extra; filters+=sfx_filters; labels+=sfx_labels
        filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=first:normalize=0[mixed]')
        mastering = ''
        if timeline.normalize_audio:
            # Measure the actual mixed programme, then apply the measured values.
            measure_inputs = inputs.copy()
            measure_inputs[2] = 'info'
            jobs.report(.86,'Measuring loudness for mastering')
            measure = run(measure_inputs + ['-filter_complex',';'.join(filters)+
                ';[mixed]loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json[measured]',
                '-map','[measured]','-t',str(duration),'-f','null','-'])
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
        jobs.report(.9,'Encoding the final video')
        run(inputs + ['-filter_complex_threads','1','-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[audio]',
                      '-c:v','libx264','-crf',crf,'-preset',preset,'-pix_fmt','yuv420p','-threads','2',
                      '-c:a', 'aac', '-b:a', '320k', '-t', str(duration),
                      '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
                      '-movflags', '+faststart', str(pending)])
        jobs.report(.97,'Validating the export (full decode)')
        report = validate_output(pending, settings, duration)
        report['audio_mastering'] = 'measured two-pass loudnorm' if timeline.normalize_audio else 'peak limiter'
        report['edit_effects'] = sorted({c.speed_profile for c in timeline.clips} |
                                        ({'beat_punch'} if any(c.accents for c in timeline.clips) else set()))
        report['finishing'] = dict(interpolation=timeline.interpolation, look=timeline.look,
                                   motion_blur=timeline.motion_blur, reframe=timeline.reframe, sfx=timeline.sfx,
                                   sfx_count=sum(b.get('effect') in craft.SWISH_EFFECTS for b in boundaries)
                                   if timeline.sfx=='swish' else 0)
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


def create_montage(gameplay, music, output, settings, story=None, ai_model=None, brief=None, ai_editor=None):
    output = Path(output).resolve()
    sidecars = [output.with_suffix('.timeline.json'), output.with_suffix('.analysis.json'),
                output.with_suffix('.validation.json')]
    if output.exists() or any(p.exists() for p in sidecars):
        raise FileExistsError('Output or its project sidecars already exist')
    jobs.report(0,'Reading your clips and song')
    sources = [probe(p) for p in gameplay]
    if len({s['path'] for s in sources}) != len(sources):
        raise ValueError('Duplicate gameplay inputs')
    song = probe(music)
    duration = min(settings.duration, song['duration'])
    music_start = 0.0
    override = story.get('beat_override') if story else None
    if story and story.get('auto_music_section'):
        LOG.info('Selecting an energetic section of the chosen soundtrack')
        whole = music_analysis(song, song['duration'], override=override)
        starts = drops = None
        if rhythm_usable(whole):
            # Begin on a measured downbeat, preferring four-bar/energy phrase starts.
            phrases = [p['time'] for p in whole['phrases']]
            starts = phrases if any(t <= song['duration']-duration for t in phrases) else whole['downbeats']
            drops = [p['time'] for p in whole['phrases'] if 'drop' in p['kinds']]
        music_start = choose_section(whole['energy'],song['duration'],duration,starts=starts,drops=drops)
    jobs.report(.06,'Finding the beat, bars and drops')
    analysis = music_analysis(song, duration, start=music_start, override=override)
    if story and story.get('auto_music_section') and rhythm_usable(whole):
        analysis.update(excerpt_grid(whole, music_start, duration))
        analysis['cut_mode'] = 'beats (manual grid)' if override else 'beats'
    candidates = []
    screen_report = {}
    for number, source in enumerate(sources):
        LOG.info('Analyzing %s', source['path'])
        jobs.report(.12+.23*number/len(sources), f'Analysing gameplay {number+1} of {len(sources)}')
        candidates.extend(analyze_gameplay(source, settings, screen_report))
    ai_plan = None
    vision = None
    if ai_editor is not None:
        LOG.info('Requesting Claude vision review of candidate moments')
        jobs.report(.36,'Claude is reviewing your best moments')
        candidates, vision = ai_editor.review(candidates, brief or '')
    if ai_model:
        from .ai_director import OllamaDirector, configure_plan, DEFAULT_BRIEF
        LOG.info('Requesting local Ollama director plan')
        plan,pool = OllamaDirector(ai_model).plan(candidates,brief or DEFAULT_BRIEF)
        candidates,settings = configure_plan(plan,pool,settings)
        ai_plan = {'provider':'ollama','model':ai_model,'plan':plan,
                   'evidence':'motion/audio metadata only; no visual semantic analysis'}
    timeline = direct(candidates, analysis, song['path'], settings, duration, ordered=bool(ai_model),cinematic=bool(story and story.get('edit_profile')=='cinematic'))
    timeline = replace(timeline,music_start=music_start)
    if vision is not None and hasattr(ai_editor, 'review_cut'):
        LOG.info('Requesting Claude review of the planned cut')
        jobs.report(.42,'Claude is reviewing the cut')
        try:
            timeline, vision['cut_review'] = ai_editor.review_cut(timeline, candidates, analysis, brief or '')
        except ValueError as error:
            # The first-pass plan is already valid; a failed review keeps it and says why.
            vision['cut_review'] = {'error': str(error)}
    if ai_plan:
        timeline = replace(timeline,transition=plan['transition'],transition_duration=plan['transition_duration'])
    if story is not None:
        timeline = replace(timeline, dialogue=[DialogueCue(**c) for c in story.get('dialogue', [])],
                           transition=story.get('transition', timeline.transition) if not ai_model else timeline.transition,
                           transition_duration=story.get('transition_duration', timeline.transition_duration) if not ai_model else timeline.transition_duration,
                           faith_message=story.get('faith_message',''),gameplay_gain=story.get('gameplay_gain',0),
                           music_gain=story.get('music_gain',1),normalize_audio=story.get('normalize_audio',False),
                           interpolation=story.get('interpolation','none'),look=story.get('look','none'),
                           motion_blur=bool(story.get('motion_blur',False)),sfx=story.get('sfx','none'),
                           reframe=('follow' if settings.height>settings.width else 'fit')
                                   if story.get('reframe','fit')=='auto' else story.get('reframe','fit'))
    if timeline.transition == 'cinematic' and str(analysis.get('cut_mode')).startswith('beats'):
        timeline = replace(timeline, boundary_transitions=boundary_styles(timeline, analysis))
    jobs.report(.45,'Rendering')
    with jobs.span(.45, 1.0):
        report = render(timeline, output)
    timeline.save(sidecars[0])
    sidecars[1].write_text(json.dumps({'music': analysis, 'candidates': candidates, 'ai_director': ai_plan,
                                       'ai_editor': vision,
                                       'screen_analysis': screen_report}, indent=2))
    report['ai_director'] = 'ollama' if ai_model else ('claude vision' if vision else 'heuristic')
    if vision:
        report['ai_editor'] = {k: vision[k] for k in ('model','reviewed','usable','events') if k in vision}
    report['requested_duration'] = settings.duration
    report['shortened'] = sum(c.duration for c in timeline.clips) < settings.duration-.01
    report['music_alignment'] = alignment_report(timeline, analysis)
    sidecars[2].write_text(json.dumps(report, indent=2))
    return report
