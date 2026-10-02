"""Bounded retiming with an explicit, replayable output-to-source mapping."""

import math

RAMP = ((0.25, 1.4), (0.5, 0.6), (0.25, 1.4))
# Smooth velocity curve: speed(o) = 1 + DEPTH*cos(2*pi*o/D), 1.5x at the shot edges easing
# to 0.5x at its centre. Sampled at KNOTS segments; the piecewise-linear source mapping is
# the exact one rendered, so anchors and render agree to the sample.
DEPTH, KNOTS = 0.5, 16
PROFILES = ('normal', 'impact', 'ramp')


def ramp_knots(duration):
    outputs = [duration*k/KNOTS for k in range(KNOTS+1)]
    sources = [o+DEPTH*duration/(2*math.pi)*math.sin(2*math.pi*o/duration) for o in outputs]
    sources[0], sources[-1] = 0.0, duration
    return outputs, sources


def source_offset(output_offset, duration, profile):
    if profile == 'normal':
        return output_offset
    if profile == 'ramp':
        outputs, sources = ramp_knots(duration)
        for k in range(KNOTS):
            if output_offset <= outputs[k+1]+1e-12 or k == KNOTS-1:
                fraction = (output_offset-outputs[k])/(outputs[k+1]-outputs[k])
                return sources[k]+fraction*(sources[k+1]-sources[k])
    consumed = 0
    remaining = output_offset
    for fraction, speed in RAMP:
        amount = min(remaining, duration * fraction)
        consumed += amount * speed
        remaining -= amount
        if remaining <= 1e-9:
            break
    return consumed


def retime_filters(duration, profile, audio):
    """Fast/slow/fast consumes exactly duration seconds, preserving cut anchors."""
    if profile == 'normal':
        filters = [f'[0:v]trim=duration={duration},setpts=PTS-STARTPTS[vret]']
        if audio:
            filters.append(f'[0:a]atrim=duration={duration},asetpts=PTS-STARTPTS[aret]')
        return filters
    if profile == 'ramp':
        outputs, sources = ramp_knots(duration)
        # Invert the piecewise-linear mapping in one setpts expression (T = source time).
        def piece(k):
            slope = (outputs[k+1]-outputs[k])/(sources[k+1]-sources[k])
            return f'{outputs[k]:.9f}+(T-{sources[k]:.9f})*{slope:.9f}'
        expression = piece(KNOTS-1)
        for k in range(KNOTS-2, -1, -1):
            expression = f'if(lt(T,{sources[k+1]:.9f}),{piece(k)},{expression})'
        filters = [f"[0:v]trim=duration={duration},setpts=PTS-STARTPTS,setpts='({expression})/TB'[vret]"]
        if audio:
            labels = ''.join(f'[a{k}]' for k in range(KNOTS))
            filters.append(f'[0:a]asplit={KNOTS}{labels}')
            for k in range(KNOTS):
                speed = (sources[k+1]-sources[k])/(outputs[k+1]-outputs[k])
                filters.append(f'[a{k}]atrim=start={sources[k]:.9f}:end={sources[k+1]:.9f},'
                               f'asetpts=PTS-STARTPTS,atempo={max(.5, speed):.6f}[s{k}]')
            filters.append(''.join(f'[s{k}]' for k in range(KNOTS))+f'concat=n={KNOTS}:v=0:a=1[aret]')
        return filters
    filters = ['[0:v]split=3[v0][v1][v2]']
    if audio:
        filters.append('[0:a]asplit=3[a0][a1][a2]')
    cursor = 0
    for i, (fraction, speed) in enumerate(RAMP):
        end = cursor + duration * fraction * speed
        filters.append(f'[v{i}]trim=start={cursor}:end={end},setpts=(PTS-STARTPTS)/{speed}[r{i}]')
        if audio:
            filters.append(f'[a{i}]atrim=start={cursor}:end={end},asetpts=PTS-STARTPTS,atempo={speed}[s{i}]')
        cursor = end
    filters.append('[r0][r1][r2]concat=n=3:v=1:a=0[vret]')
    if audio:
        filters.append('[s0][s1][s2]concat=n=3:v=0:a=1[aret]')
    return filters
