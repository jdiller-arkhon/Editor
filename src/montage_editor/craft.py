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
INTERPOLATION = ('none', 'blend', 'motion')
REFRAME = ('fit', 'follow')
SFX = ('none', 'swish')
SWISHES = sorted((Path(__file__).parent/'resources'/'sfx').glob('swish-*.ogg'))
SWISH_EFFECTS = {'smoothleft', 'smoothright', 'zoomin', 'hblur'}
SWISH_GAIN, SWISH_LEAD = .3, .06


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
