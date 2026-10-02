"""Measured tempo, beat, downbeat and phrase evidence from a local soundtrack.

Everything here is derived from the decoded audio's spectral-flux envelope and RMS
energy. Beats are tracked with dynamic programming over a single estimated tempo;
downbeats are the 4/4 beat phase with the strongest low-frequency accents. Phrase
boundaries are either an assumed four-bar grid or a measured bar-energy change and
are labelled as such. None of this recognises lyrics, sections or genre.
"""
import numpy as np

METHOD = ('autocorrelation tempo, dynamic-programming beat tracking, low-band accent plus '
          'timbre-novelty downbeat phase (assumes 4/4), four-bar grid, measured bar-energy changes '
          'and bass-entrance drops')
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


def _envelope_mean(values, start, end, hop):
    lo, hi = int(start/hop), max(int(start/hop)+1, int(end/hop))
    return float(np.mean(values[lo:hi])) if lo < len(values) else 0.0


def structure(downbeats, bar_seconds, energy, energy_hop=.05, bass=None, bass_hop=.01):
    """Bars and phrase marks from a downbeat grid.

    ``grid`` every four bars is an assumption; ``rise``/``fall`` are measured bar-energy
    changes; ``drop`` is a measured bass entrance (bar bass at least twice the previous two
    bars and loud overall); ``build`` marks the start of a rising run of bars into a drop.
    """
    bars = []
    for i, start in enumerate(downbeats):
        end = downbeats[i+1] if i+1 < len(downbeats) else start+bar_seconds
        bar = dict(start=round(float(start), 4), energy=_envelope_mean(energy, start, end, energy_hop))
        if bass is not None and len(bass):
            bar['bass'] = _envelope_mean(bass, start, end, bass_hop)
        bars.append(bar)
    phrases = []
    levels = np.asarray([b['energy'] for b in bars])
    lows = np.asarray([b.get('bass', 0.0) for b in bars])
    scale, low_scale = (float(levels.max()) if len(levels) else 0.0), (float(lows.max()) if len(lows) else 0.0)

    def repeated(kind, i):
        return bool(phrases) and phrases[-1]['bar'] == i-1 and kind in phrases[-1]['kinds']
    for i, bar in enumerate(bars):
        kinds = []
        if i and i % 4 == 0:
            kinds.append('grid')
        if i >= 2 and scale > 0:
            before = float(levels[i-2:i].mean())
            change = levels[i]-before
            kind = 'rise' if change > 0 else 'fall'
            if (abs(change) >= .2*scale and (before <= 0 or not .7 <= levels[i]/before <= 1.4)
                    and not repeated(kind, i)):
                kinds.append(kind)
        if i >= 2 and low_scale > 0:
            before = float(lows[i-2:i].mean())
            if lows[i] >= .35*low_scale and lows[i] >= 2*max(before, 1e-12) and not repeated('drop', i):
                kinds.append('drop')
        if kinds:
            phrases.append(dict(time=bar['start'], bar=i, kinds=kinds))
    # A build is a run of at least two bars of rising energy that ends at a drop.
    for phrase in [p for p in phrases if 'drop' in p['kinds']]:
        j = phrase['bar']
        k = j
        while k-1 >= 0 and levels[k-1] < levels[k]*1.0001 and j-k < 4:
            k -= 1
        if j-k >= 2:
            existing = next((p for p in phrases if p['bar'] == k), None)
            if existing:
                if 'build' not in existing['kinds']:
                    existing['kinds'].append('build')
            else:
                phrases.append(dict(time=bars[k]['start'], bar=k, kinds=['build']))
    phrases.sort(key=lambda p: p['bar'])
    return bars, phrases


def beat_grid(onset, low_onset, energy, hop=.01, energy_hop=.05, latency=0.0, bass=None, timbre=None):
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
    if timbre is not None and len(timbre) > frames[-1]:
        # Chords and arrangement tend to change on downbeats: beat-synchronous timbre novelty.
        timbre = np.asarray(timbre, dtype=float)
        bounds = list(frames)+[min(len(timbre), frames[-1]+int(round(period)))]
        means = np.asarray([timbre[a:max(a+1, b)].mean(axis=0) for a, b in zip(bounds[:-1], bounds[1:])])
        novelty = np.r_[0.0, np.linalg.norm(np.diff(means, axis=0), axis=1)]
        accent = accent+.6*novelty/(novelty.max() or 1)
    phase_strength = [float(accent[p::4].mean()) for p in range(4)]
    ranked = sorted(phase_strength, reverse=True)
    phase = int(np.argmax(phase_strength))
    downbeat_confidence = float((ranked[0]-ranked[1])/ranked[0]) if ranked[0] > 0 else 0.0
    downbeats = times[phase::4]
    bars, phrases = structure(downbeats, 4*slope*hop, energy, energy_hop, bass, hop)
    return dict(tempo_bpm=round(float(tempo), 2), beats=[round(float(t), 4) for t in times],
                downbeats=[round(float(t), 4) for t in downbeats], bars=bars, phrases=phrases,
                confidence=round(confidence, 3), periodicity=round(periodicity, 3),
                beat_alignment=round(alignment, 3), steadiness=round(steadiness, 3),
                downbeat_confidence=round(downbeat_confidence, 3), method=METHOD)


def manual_grid(bpm, first_downbeat, duration, energy, energy_hop=.05, bass=None, bass_hop=.01):
    """User-corrected grid: ``first_downbeat`` is in analysis time (may be negative)."""
    if not (isinstance(bpm, (int, float)) and 40 <= bpm <= 240):
        raise ValueError('Tempo override must be between 40 and 240 BPM')
    period = 60/float(bpm)
    first = float(first_downbeat) % (4*period)
    beats = np.arange(first-4*period, duration+1e-9, period)
    beats = beats[beats >= 0]
    downbeats = np.arange(first, duration+1e-9, 4*period)
    bars, phrases = structure(downbeats, 4*period, np.asarray(energy, float), energy_hop, bass, bass_hop)
    return dict(tempo_bpm=round(float(bpm), 2), beats=[round(float(t), 4) for t in beats],
                downbeats=[round(float(t), 4) for t in downbeats], bars=bars, phrases=phrases,
                confidence=1.0, periodicity=None, beat_alignment=None, steadiness=None,
                downbeat_confidence=None, method='manual tempo and downbeat override (user-corrected)')


def smoothed_energy(energy, hop):
    energy = np.asarray(energy, dtype=float)
    width = max(1, int(round(1/hop)))
    return np.convolve(energy, np.ones(width)/width, mode='same') if len(energy) else energy


def excerpt_grid(whole, start, duration):
    """Shift a whole-song grid into excerpt time, keeping its bar/phrase numbering and
    its energy scale (an excerpt re-analysed alone loses edge beats and calls a
    uniformly loud chorus 'medium')."""
    inside = lambda t: -1e-6 <= t-start <= duration+1e-6
    shift = lambda t: round(float(t-start), 4)
    smooth = smoothed_energy(whole['energy'], whole.get('hop_seconds', .05))
    return dict(beats=[shift(t) for t in whole['beats'] if inside(t)],
                downbeats=[shift(t) for t in whole['downbeats'] if inside(t)],
                bars=[dict(b, start=shift(b['start'])) for b in whole['bars'] if inside(b['start'])],
                phrases=[dict(p, time=shift(p['time'])) for p in whole['phrases'] if inside(p['time'])],
                tempo_bpm=whole['tempo_bpm'], beat_confidence=whole['beat_confidence'],
                beat_evidence=dict(whole['beat_evidence'], source='whole-song grid shifted to excerpt'),
                energy_reference=[float(np.quantile(smooth, .05)), float(np.quantile(smooth, .95))])


def usable(music):
    return bool(music.get('beats')) and music.get('beat_confidence', 0) >= MINIMUM_CONFIDENCE


def plan_cuts(music, settings, duration, bursts=False):
    """Choose cut points on tracked beats with a global dynamic-programming path.

    Shots end on beats (or the programme end), favouring downbeats, phrase boundaries
    and 2/4/8/16-beat lengths; higher local energy asks for shorter shots. Returns a
    list of (length, tags) with frame-quantized lengths summing to ``duration``, or an
    empty list when the clip-length bounds cannot be met from this beat grid.

    Repeating the previous shot's length is mildly penalised so steady sections vary. With
    ``bursts``, the two bars following the bar after a drop or lift may cut in double time (2-beat shots, or
    1-beat shots for slow songs) below ``minimum_clip``.
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
        energy = smoothed_energy(energy, hop)
        floor, scale = music.get('energy_reference') or (float(np.quantile(energy, .05)),
                                                         float(np.quantile(energy, .95)))
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
        reward.append((.35 if near(downbeats, t) else 0)+(.8+(.4 if 'rise' in kinds or 'drop' in kinds else 0)
                                                         if kinds else 0))
    reward.append(.5)
    period = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.0
    burst_beats = 1 if period >= .55 else 2
    # The drop shot itself stays long enough for its impact ramp; the burst follows a bar later.
    windows = [(t+4*period-tolerance, t+12*period+tolerance) for t, k in phrases if 'drop' in k or 'rise' in k] \
        if bursts and period else []
    in_burst = lambda a, b: any(lo <= a and b <= hi for lo, hi in windows)
    # Search state: (node, length in frames of the shot that ended there) -> (score, back state).
    best = [dict() for _ in times]
    best[0][0] = (0.0, None)
    for j in range(1, len(times)):
        for i in range(j-1, -1, -1):
            length = times[j]-times[i]
            if length > settings.maximum_clip+tolerance:
                break
            if not best[i]:
                continue
            short = length < settings.minimum_clip-tolerance
            beats_here = beat_index[j]-beat_index[i] if beat_index[j] is not None else None
            if short and not (beats_here == burst_beats and in_burst(times[i], times[j])):
                continue
            if short:
                base = reward[j]+.35   # a deliberate double-time burst after the drop
            else:
                target = settings.maximum_clip-level(times[i], times[j])*span
                base = reward[j]-abs(length-target)/max(span, .25)
                if beats_here in (2, 4, 8, 16):
                    base += .2
            crossed = [t for t, k in phrases if times[i]+tolerance < t < times[j]-tolerance]
            base -= 1.2*len(crossed)
            key = round(length*fps)
            for previous, (score, _) in best[i].items():
                total = score+base-(.15 if previous == key and not short else 0)
                if key not in best[j] or total > best[j][key][0]:
                    best[j][key] = (total, (i, previous))
    if not best[-1]:
        return []
    path, j = [], len(times)-1
    key = max(best[-1], key=lambda k: best[-1][k][0])
    while j > 0:
        i, previous = best[j][key][1]
        path.append((i, j))
        j, key = i, previous
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
                                  interior_downbeats=[float(b-start) for b in downbeats
                                                      if start+tolerance < b < end-tolerance],
                                  interior_beats=[float(b-start) for b in beats
                                                  if start+tolerance < b < end-tolerance],
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


def boundary_styles(timeline, music):
    """Hard cuts on ordinary beats; composited blends only where the music turns.

    Lifts get a zoom-through, four-bar phrase turns alternate directional pushes,
    energy falls dissolve. Every choice is tied to a measured or labelled phrase mark.
    """
    tolerance = .5/timeline.settings['fps']+1e-6
    styles, position, pushes = [], 0.0, 0
    for clip in timeline.clips[:-1]:
        position += clip.duration
        kinds = next((p['kinds'] for p in music.get('phrases', [])
                      if abs(p['time']-position) <= tolerance), [])
        if 'rise' in kinds or 'drop' in kinds:
            styles.append('zoomin')
        elif 'fall' in kinds:
            styles.append('fade')
        elif 'grid' in kinds:
            styles.append(('smoothleft', 'smoothright')[pushes % 2])
            pushes += 1
        else:
            styles.append('cut')
    return styles
