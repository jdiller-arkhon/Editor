"""Bounded retiming with an explicit, replayable output-to-source mapping."""

RAMP = ((0.25, 1.4), (0.5, 0.6), (0.25, 1.4))


def source_offset(output_offset, duration, profile):
    if profile == 'normal':
        return output_offset
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
