"""Deterministic soundtrack excerpt selection from measured local audio."""
import numpy as np


def choose_section(energy, source_duration, output_duration, hop=.05, starts=None):
    """Prefer an energetic, varying excerpt; this is not musical phrase recognition.

    ``starts`` may restrict candidates to measured musical positions (downbeats or
    phrase starts); otherwise excerpts begin on a one-second grid.
    """
    if output_duration >= source_duration:
        return 0.0
    energy = np.asarray(energy,dtype=float)
    if not len(energy) or not np.all(np.isfinite(energy)):
        raise ValueError('Invalid soundtrack energy analysis')
    count = max(1,round(output_duration/hop))
    last = max(0,source_duration-output_duration)
    if starts is not None:
        starts = [float(t) for t in starts if 0 <= t <= last+1e-6]
    if not starts:
        starts = list(np.arange(0,last+1e-6,1.0))
        if not starts or last-starts[-1]>.01:
            starts.append(last)
    scored = []
    for start in starts:
        excerpt = energy[round(start/hop):round(start/hop)+count]
        if not len(excerpt):
            continue
        attacks = np.maximum(np.diff(excerpt),0)
        score = float(.7*excerpt.mean()+.2*excerpt.std()+.1*(attacks.mean() if len(attacks) else 0))
        scored.append((start,score))
    maximum = max(score for start,score in scored)
    # Preserve earlier musical context when multiple windows score similarly.
    return float(next(start for start,score in scored if score>=maximum*.98))
