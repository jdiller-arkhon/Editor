"""Measured tempo, beat, downbeat and phrase evidence from a local soundtrack.

Everything here is derived from the decoded audio's spectral-flux envelope and RMS
energy. Beats are tracked with dynamic programming over a single estimated tempo;
downbeats are the 4/4 beat phase with the strongest low-frequency accents. Phrase
boundaries are either an assumed four-bar grid or a measured bar-energy change and
are labelled as such. None of this recognises lyrics, sections or genre.
"""
import numpy as np

METHOD = ('autocorrelation tempo, dynamic-programming beat tracking, low-band accent '
          'downbeat phase (assumes 4/4), four-bar grid plus measured bar-energy changes')
MINIMUM_CONFIDENCE = .5


def _strongest_near(envelope, index, radius):
    lo, hi = max(0, index-radius), min(len(envelope), index+radius+1)
    return float(envelope[lo:hi].max()) if hi > lo else 0.0


def estimate_tempo(envelope, hop, low=60, high=200, centre=120):
    """Return (bpm, period in frames, periodicity in [0, 1])."""
    onset = envelope-envelope.mean()
    size = 1 << int(np.ceil(np.log2(2*len(onset))))
    spectrum = np.fft.rfft(onset, size)
    correlation = np.fft.irfft(spectrum*np.conj(spectrum))[:len(onset)]
    if correlation[0] <= 0:
        return None, None, 0.0
    correlation = correlation/correlation[0]
    shortest, longest = int(np.floor(60/high/hop)), int(np.ceil(60/low/hop))
    longest = min(longest, len(correlation)//2-1)
    if longest <= shortest+1:
        return None, None, 0.0
    lags = np.arange(shortest, longest+1)
    bpm = 60/(lags*hop)
    # A broad log-tempo prior resolves octave ambiguity toward common montage tempi.
    prior = np.exp(-.5*(np.log2(bpm/centre)/.9)**2)
    harmonic = correlation[lags] + .5*correlation[np.minimum(2*lags, len(correlation)-1)]
    best = int(np.argmax(np.maximum(harmonic, 0)*prior))
    lag = float(lags[best])
    if 0 < best < len(lags)-1:
        a, b, c = harmonic[best-1:best+2]
        denominator = a-2*b+c
        if denominator < 0:
            lag += .5*(a-c)/denominator
    return 60/(lag*hop), lag, float(max(0.0, correlation[int(round(lag))]))


def track_beats(envelope, period, tightness=100.0):
    """Ellis-style dynamic programming: strong onsets spaced close to one period."""
    count = len(envelope)
    strength = envelope/(envelope.std() or 1)
    score = strength.copy()
    back = np.full(count, -1)
    window = np.arange(-int(round(2*period)), -int(round(period/2))+1)
    penalty = -tightness*np.log(-window/period)**2
    for t in range(count):
        previous = t+window
        valid = previous >= 0
        if not valid.any():
            continue
        candidates = score[previous[valid]]+penalty[valid]
        best = int(np.argmax(candidates))
        if candidates[best] > 0:
            score[t] = strength[t]+candidates[best]
            back[t] = previous[valid][best]
    # End on the strongest cumulative score within the final period.
    tail = max(0, count-int(round(period)))
    t = tail+int(np.argmax(score[tail:]))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    return np.asarray(beats[::-1], dtype=int)


def beat_grid(onset, low_onset, energy, hop=.01, energy_hop=.05, latency=0.0):
    """Measure a beat grid; callers must honour ``confidence`` before relying on it."""
    onset = np.asarray(onset, dtype=float)
    low_onset = np.asarray(low_onset, dtype=float)
    energy = np.asarray(energy, dtype=float)
    empty = dict(tempo_bpm=None, beats=[], downbeats=[], bars=[], phrases=[],
                 confidence=0.0, periodicity=0.0, beat_alignment=0.0, downbeat_confidence=0.0,
                 method=METHOD)
    if len(onset) < 4/hop or not np.all(np.isfinite(onset)) or onset.max() <= 0:
        return empty
    bpm, period, periodicity = estimate_tempo(onset, hop)
    if bpm is None:
        return empty
    frames = track_beats(onset, period)
    if len(frames) < 8:
        return dict(empty, tempo_bpm=round(bpm, 2), periodicity=round(periodicity, 3))
    radius = max(1, int(round(.03/hop)))
    at_beats = np.asarray([_strongest_near(onset, f, radius) for f in frames])
    # Fraction of beats on a clearly audible attack, versus the envelope's typical level.
    alignment = float(np.mean(at_beats > np.quantile(onset, .75)))
    intervals = np.diff(frames)
    steadiness = float(np.mean(np.abs(intervals-period) <= max(2, .08*period)))
    confidence = float(np.clip(min(1, periodicity/.25)*alignment*steadiness, 0, 1))
    # Regression gives sub-frame tempo precision from the tracked beat sequence.
    index = np.arange(len(frames))
    slope, intercept = np.polyfit(index, frames, 1)
    tempo = 60/(slope*hop)
    times = frames*hop+latency
    accent = np.asarray([_strongest_near(low_onset, f, radius) for f in frames])
    accent = accent/(accent.max() or 1)+.25*at_beats/(at_beats.max() or 1)
    phase_strength = [float(accent[p::4].mean()) for p in range(4)]
    ranked = sorted(phase_strength, reverse=True)
    phase = int(np.argmax(phase_strength))
    downbeat_confidence = float((ranked[0]-ranked[1])/ranked[0]) if ranked[0] > 0 else 0.0
    downbeats = times[phase::4]
    bars = []
    for i, start in enumerate(downbeats):
        end = downbeats[i+1] if i+1 < len(downbeats) else start+4*slope*hop
        lo, hi = int(start/energy_hop), max(int(start/energy_hop)+1, int(end/energy_hop))
        level = float(energy[lo:hi].mean()) if lo < len(energy) else 0.0
        bars.append(dict(start=round(float(start), 4), energy=level))
    phrases = []
    levels = np.asarray([b['energy'] for b in bars])
    scale = float(levels.max()) if len(levels) else 0.0
    for i, bar in enumerate(bars):
        kinds = []
        if i and i % 4 == 0:
            kinds.append('grid')
        if i >= 2 and scale > 0:
            before = float(levels[i-2:i].mean())
            change = levels[i]-before
            kind = 'rise' if change > 0 else 'fall'
            repeated = phrases and phrases[-1]['bar'] == i-1 and kind in phrases[-1]['kinds']
            if (abs(change) >= .2*scale and (before <= 0 or not .7 <= levels[i]/before <= 1.4)
                    and not repeated):
                kinds.append(kind)
        if kinds:
            phrases.append(dict(time=bar['start'], bar=i, kinds=kinds))
    return dict(tempo_bpm=round(float(tempo), 2), beats=[round(float(t), 4) for t in times],
                downbeats=[round(float(t), 4) for t in downbeats], bars=bars, phrases=phrases,
                confidence=round(confidence, 3), periodicity=round(periodicity, 3),
                beat_alignment=round(alignment, 3), steadiness=round(steadiness, 3),
                downbeat_confidence=round(downbeat_confidence, 3), method=METHOD)


def usable(music):
    return bool(music.get('beats')) and music.get('beat_confidence', 0) >= MINIMUM_CONFIDENCE


def plan_cuts(music, settings, duration):
    """Choose cut points on tracked beats with a global dynamic-programming path.

    Shots end on beats (or the programme end), favouring downbeats, phrase boundaries
    and 2/4/8/16-beat lengths; higher local energy asks for shorter shots. Returns a
    list of (length, tags) with frame-quantized lengths summing to ``duration``, or an
    empty list when the clip-length bounds cannot be met from this beat grid.
    """
    fps = settings.fps
    tolerance = .5/fps
    frame = lambda t: round(t*fps)/fps
    beats = [float(b) for b in music['beats'] if tolerance < b < duration-settings.minimum_clip/2]
    downbeats = np.asarray(music.get('downbeats', []), dtype=float)
    phrases = [(float(p['time']), p['kinds']) for p in music.get('phrases', [])]
    energy = np.asarray(music.get('energy', []), dtype=float)
    hop = music.get('hop_seconds', .05)
    if len(energy):
        width = max(1, int(round(1/hop)))
        energy = np.convolve(energy, np.ones(width)/width, mode='same')
        floor, scale = float(np.quantile(energy, .05)), float(np.quantile(energy, .95))
    span = settings.maximum_clip-settings.minimum_clip

    def level(a, b):
        if not len(energy) or scale <= floor:
            return .5
        window = energy[int(a/hop):max(int(a/hop)+1, int(b/hop))]
        return float(np.clip((window.mean()-floor)/(scale-floor), 0, 1)) if len(window) else .5

    def kinds_at(t):
        return next((k for time, k in phrases if abs(time-t) <= tolerance), [])

    def near(values, t):
        return bool(len(values)) and float(np.min(np.abs(values-t))) <= tolerance

    times = [0.0]+[frame(b) for b in beats]+[duration]
    beat_index = [0]+list(range(1, len(beats)+1))+[None]
    reward = [0.0]
    for t in times[1:-1]:
        kinds = kinds_at(t)
        reward.append((.35 if near(downbeats, t) else 0)+(.8+(.4 if 'rise' in kinds else 0) if kinds else 0))
    reward.append(.5)
    best, back = [-np.inf]*len(times), [-1]*len(times)
    best[0] = 0.0
    for j in range(1, len(times)):
        for i in range(j-1, -1, -1):
            length = times[j]-times[i]
            if length > settings.maximum_clip+tolerance:
                break
            if length < settings.minimum_clip-tolerance or best[i] == -np.inf:
                continue
            target = settings.maximum_clip-level(times[i], times[j])*span
            score = best[i]+reward[j]-abs(length-target)/max(span, .25)
            if beat_index[j] is not None and beat_index[j]-beat_index[i] in (2, 4, 8, 16):
                score += .2
            crossed = [t for t, k in phrases if times[i]+tolerance < t < times[j]-tolerance]
            score -= 1.2*len(crossed)
            if score > best[j]:
                best[j], back[j] = score, i
    if best[-1] == -np.inf:
        return []
    path, j = [], len(times)-1
    while j > 0:
        path.append((back[j], j))
        j = back[j]
    plan = []
    for i, j in reversed(path):
        start, end = times[i], times[j]
        length = end-start
        interior = [b-start for b in beats if start+.25*length <= b <= start+.75*length]
        strong = [b for b in interior if near(downbeats, b+start)]
        pool = strong or interior
        plan.append((length, dict(start=round(start, 4), energy=round(level(start, end), 3),
                                  on_beat=j < len(times)-1, on_downbeat=near(downbeats, end),
                                  phrase=kinds_at(end), starts_phrase=kinds_at(start),
                                  anchor=min(pool, key=lambda b: abs(b-length*.5)) if pool else length*.5)))
    return plan


def alignment_report(timeline, music):
    """Measure how the rendered cut clock lines up with the analysed music."""
    fps = timeline.settings['fps']
    tolerance = .5/fps+1e-6
    cuts, position = [], 0.0
    for clip in timeline.clips[:-1]:
        position += clip.duration
        cuts.append(position)
    beats = np.asarray(music.get('beats', []), dtype=float)
    downbeats = np.asarray(music.get('downbeats', []), dtype=float)
    phrases = np.asarray([p['time'] for p in music.get('phrases', [])], dtype=float)
    onsets = np.asarray(music.get('onsets', []), dtype=float)

    def share(values):
        if not cuts or not len(values):
            return 0.0
        return round(float(np.mean([np.min(np.abs(values-c)) <= tolerance for c in cuts])), 3)

    reachable = [p for p in phrases if 0 < p < position+1e-6]
    hit = [p for p in reachable if any(abs(p-c) <= tolerance for c in cuts)]
    return dict(mode=music.get('cut_mode', 'attacks'), cuts=len(cuts), on_beat=share(beats),
                on_downbeat=share(downbeats), on_attack=share(onsets),
                phrase_boundaries_cut=f'{len(hit)}/{len(reachable)}',
                tempo_bpm=music.get('tempo_bpm'), beat_confidence=music.get('beat_confidence'))

