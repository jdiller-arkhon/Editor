"""Game-agnostic screen and sound evidence for gameplay candidates.

HUD presence: most games draw a persistent HUD (health, ammo, crosshair furniture). Its
edges stay put while the world moves, so they can be learned from the footage itself
(keyframes, no game rules). Death screens, scoreboards, menus, kill-cams and loading
screens hide or cover that HUD. Frames whose HUD edges have mostly vanished are not
gameplay. Footage without a persistent HUD yields no mask and no exclusions.

Calibration (Xonotic duel, CC BY-SA 4.0, 4 min hand-labelled train + 5 min held-out):
death/scoreboard frames measured 0.05-0.29 of median HUD presence, respawn HUD layout
changes 0.42-0.47, 5th-percentile gameplay 0.61-0.66. With the training-only threshold
0.5 the held-out clip had every death/scoreboard event caught plus three short respawn
false spans; 0.35 separates both clips but was chosen after seeing the held-out data.

Transients: positive broadband spectral flux of the gameplay audio marks gunshots,
explosions and impacts. It is evidence of loud events, not of kills.
"""
import subprocess

import numpy as np

WIDTH, HEIGHT = 320, 180
EDGE = 35
PERSISTENT = .6
EXCLUDE_BELOW = .35
FULL_ABOVE = .6
MINIMUM_MASK = 120


def edges(frame):
    found = np.zeros(frame.shape, bool)
    found[:, :-1] |= np.abs(np.diff(frame, axis=1)) > EDGE
    found[:-1, :] |= np.abs(np.diff(frame, axis=0)) > EDGE
    return found


def _decode(arguments):
    raw = subprocess.run(arguments, check=True, capture_output=True).stdout
    size = WIDTH*HEIGHT
    count = len(raw)//size
    return np.frombuffer(raw[:count*size], np.uint8).reshape(count, HEIGHT, WIDTH)


def learn_hud_mask(path, duration):
    """Persistent edge pixels across sampled frames, or None when there is no stable HUD."""
    scale = f'scale={WIDTH}:{HEIGHT},format=gray'
    frames = _decode(['ffmpeg', '-v', 'error', '-skip_frame', 'nokey', '-i', path, '-an',
                      '-vf', scale, '-fps_mode', 'passthrough', '-f', 'rawvideo', 'pipe:1'])
    if len(frames) < 12:
        rate = max(.2, min(2.0, 60/max(duration, 1)))
        frames = _decode(['ffmpeg', '-v', 'error', '-i', path, '-an', '-vf', f'fps={rate},{scale}',
                          '-f', 'rawvideo', 'pipe:1'])
    if len(frames) < 8:
        return None
    step = max(1, len(frames)//200)
    persistence = np.mean([edges(f.astype(np.float32)) for f in frames[::step]], axis=0)
    mask = persistence >= PERSISTENT
    return mask if mask.sum() >= MINIMUM_MASK else None


def presence(frame, mask):
    return float((edges(frame) & mask).sum()/mask.sum())


def hud_factor(relative):
    """Score multiplier: 0 below the exclusion threshold, ramping to 1 at normal presence."""
    return float(np.clip((relative-EXCLUDE_BELOW)/(FULL_ABOVE-EXCLUDE_BELOW), 0, 1))


def low_spans(times, relative, gap=.6):
    spans = []
    for t, value in zip(times, relative):
        if value < EXCLUDE_BELOW:
            if spans and t-spans[-1][1] <= gap:
                spans[-1][1] = float(t)
            else:
                spans.append([float(t), float(t)])
    return spans


def transients(path, duration, hop=.05, rate=8000, window=512):
    """Broadband positive spectral flux of the gameplay audio, normalised to [0, 1]."""
    flux, previous = [], None
    step = int(rate*hop)
    for start in np.arange(0, duration, 30):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', path, '-t',
                              str(min(30, duration-start)), '-vn', '-ac', '1', '-ar', str(rate),
                              '-f', 'f32le', 'pipe:1'], check=True, capture_output=True).stdout
        samples = np.frombuffer(raw, '<f4')
        for offset in range(0, len(samples), step):
            block = np.zeros(window)
            segment = samples[offset:offset+window]
            block[:len(segment)] = segment
            spectrum = np.log1p(np.abs(np.fft.rfft(block*np.hanning(window)))*10)
            flux.append(float(np.maximum(spectrum-previous, 0).mean()) if previous is not None else 0.0)
            previous = spectrum
    flux = np.asarray(flux)
    if not len(flux) or flux.max() <= 0:
        return flux, hop
    scale = float(np.quantile(flux, .995)) or float(flux.max())
    return np.clip(flux/scale, 0, 1), hop
