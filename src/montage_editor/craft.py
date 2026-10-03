"""Finishing treatments: colour looks, slow-motion interpolation, motion blur, action-following
vertical reframing and transition sound effects. All are FFmpeg filters applied inside the
existing lossless per-shot render; none changes shot timing.
"""
from pathlib import Path
import subprocess

from . import jobs

import numpy as np

LOOKS = {
    'none': '',
    'clean': 'eq=contrast=1.04:saturation=1.08',
    'punchy': 'eq=contrast=1.12:saturation=1.25:gamma=0.98,unsharp=5:5:0.35',
    'cinematic': 'eq=contrast=1.08:saturation=1.04,colorbalance=rs=-0.03:bs=0.05:rh=0.05:bh=-0.03',
    'mono': 'hue=s=0,eq=contrast=1.1',
}
# Cinematic grade plus fine moving grain (texture that also hides banding in dark scenes).
LOOKS['film'] = LOOKS['cinematic']+',noise=c0s=5:c0f=t+u'
INTERPOLATION = ('none', 'blend', 'motion')
REFRAME = ('fit', 'follow')
SFX = ('none', 'swish')
SWISHES = sorted((Path(__file__).parent/'resources'/'sfx').glob('swish-*.ogg'))
SWISH_EFFECTS = {'smoothleft', 'smoothright', 'zoomin', 'hblur'}
SWISH_GAIN, SWISH_LEAD = .3, .06
TITLE_FONT = Path(__file__).parent/'resources'/'fonts'/'Sora-700.ttf'


def interpolation_filter(mode, source_fps, out_fps, width, height):
    """Synthesise in-between frames so 0.5x slow motion is not a run of held frames.

    Applied at delivery size (cheaper, and the later scale is then a no-op). Sources that
    already have at least twice the output frame rate need nothing.
    """
    if mode == 'none' or source_fps >= 2*out_fps-1:
        return ''
    size = f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos'
    if mode == 'blend':
        return f'{size},framerate=fps={2*out_fps}'
    return f'{size},minterpolate=fps={2*out_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1'


def motion_blur_filter():
    """Simulated shutter: blend each output frame with its neighbours."""
    return 'tmix=frames=3:weights=1 2 1'


def follow_track(path, start, duration, rate=4):
    """Normalised horizontal action centre (0-1) over the shot, from frame-difference mass.

    Heavily smoothed with a dead zone, so first-person footage (motion everywhere) stays centred
    and the crop only travels when the action is clearly off-centre.
    """
    width, height = 160, 90
    raw = jobs.run(['ffmpeg', '-v', 'error', '-ss', f'{start:.3f}', '-i', path, '-t', f'{duration:.3f}',
                          '-an', '-vf', f'fps={rate},scale={width}:{height},format=gray', '-f', 'rawvideo',
                          'pipe:1']).stdout
    frames = np.frombuffer(raw[:len(raw)//(width*height)*width*height], np.uint8).reshape(-1, height, width)
    columns = np.arange(width)/(width-1)
    centres, previous = [], None
    for frame in frames.astype(np.float32):
        if previous is None:
            centres.append(.5)
        else:
            mass = np.abs(frame-previous).sum(axis=0)
            total = mass.sum()
            spread = (mass > mass.mean()*2).mean() if total else 1
            centre = float((mass*columns).sum()/total) if total else .5
            # Motion over most of the frame (camera moving) carries no direction.
            centres.append(centre if spread < .45 else .5)
        previous = frame
    if not centres:
        return [(0.0, .5)]
    smooth, value = [], centres[0]
    for centre in centres:
        target = centre if abs(centre-.5) > .08 else .5
        value += .25*(target-value)
        smooth.append(value)
    return [(i/rate, float(np.clip(v, 0, 1))) for i, v in enumerate(smooth)]


def follow_crop(track, crop_width):
    """crop filter whose x follows ``track`` (piecewise linear in segment time ``t``)."""
    def x_of(centre):
        return f'max(0,min(iw-{crop_width},iw*{centre:.4f}-{crop_width}/2))'
    expression = x_of(track[-1][1])
    for (t0, c0), (t1, c1) in reversed(list(zip(track[:-1], track[1:]))):
        piece = x_of(c0) if abs(c1-c0) < 1e-4 else \
            f'max(0,min(iw-{crop_width},iw*({c0:.4f}+(t-{t0:.3f})*{(c1-c0)/max(t1-t0, 1e-6):.5f})-{crop_width}/2))'
        expression = f'if(lt(t,{t1:.3f}),{piece},{expression})'
    return f"crop=w={crop_width}:h=ih:x='{expression}':y=0"


def swish_inputs(boundaries, start_index):
    """FFmpeg inputs and mix labels for swishes on directional/zoom blends."""
    inputs, filters, labels = [], [], []
    if not SWISHES:
        return inputs, filters, labels
    for n, boundary in enumerate(b for b in boundaries if b.get('effect') in SWISH_EFFECTS):
        index = start_index+len(inputs)//2
        inputs += ['-i', str(SWISHES[n % len(SWISHES)])]
        delay = max(0, round((boundary['at']-SWISH_LEAD)*1000))
        filters.append(f'[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume={SWISH_GAIN},'
                       f'adelay={delay}:all=1[sfx{n}]')
        labels.append(f'[sfx{n}]')
    return inputs, filters, labels


MATCH_STRENGTH = .6          # move 60% of the way toward the montage median
GAMMA_LIMITS = (.8, 1.25)
TINT_LIMIT = .05
TINT_STRENGTH = .35        # colour is often deliberate in games (lit areas), so only nudge it
TINT_APPLY = .004          # ~1 level in 8-bit; smaller corrections are skipped as invisible


def shot_statistics(path, start, duration, samples=3, width=64, height=36):
    """Mean luma (0-1) and mean R, G, B (0-1) over a few frames inside the shot."""
    values = []
    for k in range(samples):
        at = start+duration*(k+.5)/samples
        raw = jobs.run(['ffmpeg', '-v', 'error', '-ss', f'{at:.3f}', '-i', path, '-frames:v', '1', '-vf',
                        f'scale={width}:{height}', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1']).stdout
        if len(raw) == width*height*3:
            values.append(np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(float).mean(axis=0)/255)
    if not values:
        return None
    rgb = np.mean(values, axis=0)
    return dict(luma=float(.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]), rgb=[float(v) for v in rgb])


def match_filters(statistics):
    """Bounded per-shot eq/colorbalance filters pulling each shot toward the montage median."""
    known = [s for s in statistics if s and s['luma'] > .02]
    if len(known) < 2:
        return ['' for _ in statistics], [None for _ in statistics]
    target = float(np.median([s['luma'] for s in known]))
    ratios = np.median([np.asarray(s['rgb'])/max(np.mean(s['rgb']), 1e-6) for s in known], axis=0)
    filters, details = [], []
    for s in statistics:
        if not s or s['luma'] <= .02:
            filters.append(''); details.append(None); continue
        wanted = s['luma']+(target-s['luma'])*MATCH_STRENGTH
        gamma = float(np.clip(np.log(max(s['luma'], 1e-3))/np.log(min(max(wanted, 1e-3), .999)), *GAMMA_LIMITS))
        own = np.asarray(s['rgb'])/max(np.mean(s['rgb']), 1e-6)
        tint = np.clip((ratios-own)*TINT_STRENGTH, -TINT_LIMIT, TINT_LIMIT)
        parts = []
        if abs(gamma-1) > .02:
            parts.append(f'eq=gamma={gamma:.3f}')
        if np.abs(tint).max() > TINT_APPLY:
            parts.append(f'colorbalance=rm={tint[0]:.3f}:gm={tint[1]:.3f}:bm={tint[2]:.3f}:'
                         f'rh={tint[0]:.3f}:gh={tint[1]:.3f}:bh={tint[2]:.3f}')
        filters.append(','.join(parts))
        details.append(dict(gamma=round(gamma, 3), tint=[round(float(v), 3) for v in tint]))
    return filters, details


IMPACT_FLASH = .22         # brightness lift on the hit frames (eq brightness, -1..1)
IMPACT_FRAMES = 2


def impact_filter(at, fps):
    """Impact frame: a two-frame exposure flash exactly on the hit (output time ``at``)."""
    end = at+IMPACT_FRAMES/fps
    return f"eq=brightness={IMPACT_FLASH}:contrast=1.08:enable='between(t,{at:.4f},{end:.4f})'"


PAN_MINIMUM = 1.5          # pixels per frame at 160 px width: below this the camera is ~still


def pan_velocity(path, at, span=.3, width=160, height=90):
    """Horizontal image motion (px/frame at 160 px wide) just before ``at``; negative = content moves left.

    Best horizontal shift between consecutive frames (mean absolute difference over a ±12 px
    search): a camera turning right moves the image left. Plain search, not phase correlation,
    because animated HUD/effects produce competing correlation peaks.
    """
    rate, reach = 15, 12
    raw = jobs.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0.0, at-span):.3f}', '-i', path, '-t', f'{span:.3f}',
                    '-an', '-vf', f'fps={rate},scale={width}:{height},format=gray', '-f', 'rawvideo',
                    'pipe:1']).stdout
    frames = np.frombuffer(raw[:len(raw)//(width*height)*width*height], np.uint8).reshape(-1, height, width)
    shifts = []
    for a, b in zip(frames[:-1].astype(np.float32), frames[1:].astype(np.float32)):
        errors = [np.abs(a[:, reach-d:width-reach-d]-b[:, reach:width-reach]).mean() for d in range(-reach, reach+1)]
        best = int(np.argmin(errors))
        if errors[best] < .8*float(np.median(errors)):     # a clear match; flat or chaotic frames carry no pan
            shifts.append(float(best-reach))                # b(x) = a(x-d): content moved by d
    return float(np.median(shifts))*rate/30 if shifts else 0.0


def push_for_pan(velocity):
    """The push whose motion continues the camera's: content moving left → push left."""
    if abs(velocity) < PAN_MINIMUM:
        return None
    return 'smoothleft' if velocity < 0 else 'smoothright'


PULSE_LIGHT = .1             # exposure lift at the downbeat, decaying over ~0.25 s
PULSE_SPLIT = 1/240          # RGB split as a fraction of frame width, for 3 frames


def pulse_filter(times, fps, width):
    """Beat FX for one shot: an exposure pulse and a brief chromatic split on each local time."""
    if not times:
        return ''
    light = '+'.join(f'between(t,{a:.4f},{a+.3:.4f})*exp(-(t-{a:.4f})/0.08)' for a in times)
    split = max(2, round(width*PULSE_SPLIT/2)*2)
    window = '+'.join(f'between(t,{a:.4f},{a+3/fps:.4f})' for a in times)
    return (f"eq=eval=frame:brightness='{PULSE_LIGHT}*min(1,{light})',"
            f"rgbashift=rh=-{split}:bh={split}:enable='{window}'")
