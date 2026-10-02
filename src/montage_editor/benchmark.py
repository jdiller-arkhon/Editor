"""Measure a rendered montage so changes to the editor can be compared, not guessed.

Metrics come from the montage's own sidecars plus the delivered file:

- sync: share of cuts on beats/downbeats, phrase boundaries cut
- variety: distinct sources, spread across the source, visual change between neighbouring shots
- integrity: share of output built on non-gameplay spans (should be 0), full-decode validation
- highlights: share of the strongest analysed moments that made the cut, used vs available score,
  and whether the single strongest used shot sits in the most intense part of the song
- craft: ramps, punch-ins, blended vs hard cuts
- delivery: integrated loudness (LUFS) and true peak measured on the file

None of these is "quality" by itself; they make regressions and trade-offs visible. The
optional Claude judge adds a rubric grade from a contact sheet of the finished edit.
"""
import json
import re
from pathlib import Path

import numpy as np

from . import jobs
from .editing import source_offset

JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'moments': {'type': 'integer'}, 'variety': {'type': 'integer'}, 'pacing': {'type': 'integer'},
        'story': {'type': 'integer'}, 'overall': {'type': 'integer'},
        'strengths': {'type': 'string'}, 'weaknesses': {'type': 'string'},
    },
    'required': ['moments', 'variety', 'pacing', 'story', 'overall', 'strengths', 'weaknesses'],
    'additionalProperties': False,
}
JUDGE_SYSTEM = (
    'You grade finished gaming montages like a demanding senior editor. The image shows one frame '
    'from the key moment of every shot, in order; the text gives measured sync and craft statistics. '
    'Score 1-10 each: moments (are the shots genuinely strong gameplay?), variety (do shots repeat?), '
    'pacing (does the measured cutting suit the music?), story (does it build to a climax and end '
    'cleanly?), overall. Be strict: 8+ only for edits you would publish. Never infer audio you cannot '
    'hear; use the statistics. Strengths and weaknesses: under 40 words each, concrete.'
)


def _sidecars(output):
    output = Path(output)
    read = lambda suffix: json.loads(output.with_suffix(suffix).read_text())
    from .pipeline import Timeline
    return Timeline.load(output.with_suffix('.timeline.json')), read('.analysis.json'), read('.validation.json')


def loudness(output):
    stderr = jobs.run(['ffmpeg', '-v', 'info', '-nostats', '-i', str(output), '-af', 'ebur128=peak=true',
                       '-f', 'null', '-']).stderr.decode(errors='replace')
    summary = stderr[stderr.rfind('Summary:'):]
    integrated = re.search(r'I:\s+(-?[\d.]+) LUFS', summary)
    peak = re.search(r'Peak:\s+(-?[\d.]+) dBFS', summary)
    return (float(integrated.group(1)) if integrated else None, float(peak.group(1)) if peak else None)


def shot_frames(timeline, width=96, height=54):
    frames = []
    for clip in timeline.clips:
        at = clip.start+source_offset((clip.anchor_output if clip.anchor_output is not None else clip.duration/2),
                                      clip.duration, clip.speed_profile)
        raw = jobs.run(['ffmpeg', '-v', 'error', '-ss', f'{at:.3f}', '-i', clip.source, '-frames:v', '1', '-vf',
                        f'scale={width}:{height}', '-pix_fmt', 'gray', '-f', 'rawvideo', 'pipe:1']).stdout
        frames.append(np.frombuffer(raw, np.uint8).reshape(height, width).astype(float) if len(raw) == width*height
                      else np.zeros((height, width)))
    return frames


def score(output):
    timeline, analysis, validation = _sidecars(output)
    music = analysis.get('music', {})
    candidates = [c for c in analysis.get('candidates', []) if not c.get('exclude')]
    excluded = [c for c in analysis.get('candidates', []) if c.get('exclude')]
    total = sum(c.duration for c in timeline.clips)
    alignment = validation.get('music_alignment', {})
    # Integrity: output seconds built on excluded spans.
    bad = 0.0
    for clip in timeline.clips:
        for e in excluded:
            a, b = e.get('span') or (e['time']-1, e['time']+1)
            if e['source'] == clip.source:
                bad += max(0.0, min(b, clip.start+clip.duration)-max(a, clip.start))
    # Highlights: top-N analysed moments that appear inside a shot.
    covered = lambda c: any(o.source == c['source'] and o.start <= c['time'] <= o.start+o.duration
                            for o in timeline.clips)
    top = sorted(candidates, key=lambda c: -c['score'])[:len(timeline.clips)]
    used_scores = [c['score'] for c in candidates if covered(c)]
    # Hero: is the strongest used shot in the loudest third of the programme?
    energy = np.asarray(music.get('energy', []), dtype=float)
    hop = music.get('hop_seconds', .05)
    position, levels = 0.0, []
    for clip in timeline.clips:
        window = energy[int(position/hop):int((position+clip.duration)/hop)+1]
        levels.append(float(window.mean()) if len(window) else 0.0)
        position += clip.duration
    strongest = int(np.argmax([c.score for c in timeline.clips]))
    hero_on_intense = bool(levels) and bool(levels[strongest] >= np.quantile(levels, 2/3)-1e-12)
    frames = shot_frames(timeline)
    change = [float(np.abs(a-b).mean()/255) for a, b in zip(frames, frames[1:])]
    from .pipeline import probe
    lengths = {source: probe(source)['duration'] for source in {c.source for c in timeline.clips}}
    # Where in each source the shots come from (0 = start, 1 = end); low spread = one stretch reused.
    spread = [(c.start+c.duration/2)/lengths[c.source] for c in timeline.clips]
    boundaries = validation.get('transition_boundaries', [])
    integrated, peak = loudness(output)
    return dict(
        output=str(output), duration=round(total, 3), shots=len(timeline.clips),
        sync=dict(mode=alignment.get('mode'), tempo_bpm=alignment.get('tempo_bpm'), on_beat=alignment.get('on_beat'),
                  on_downbeat=alignment.get('on_downbeat'), phrase_boundaries_cut=alignment.get('phrase_boundaries_cut')),
        variety=dict(sources=len({c.source for c in timeline.clips}),
                     mean_neighbour_change=round(float(np.mean(change)), 4) if change else None,
                     min_neighbour_change=round(float(np.min(change)), 4) if change else None,
                     source_position_spread=round(float(np.std(spread)), 4) if spread else None),
        integrity=dict(non_gameplay_seconds=round(bad, 3), non_gameplay_share=round(bad/max(total, 1e-9), 4),
                       full_decode=validation.get('full_decode'), valid=validation.get('valid')),
        highlights=dict(top_moments_used=round(sum(covered(c) for c in top)/max(1, len(top)), 3),
                        mean_used_score=round(float(np.mean(used_scores)), 3) if used_scores else None,
                        mean_available_score=round(float(np.mean([c['score'] for c in candidates])), 3) if candidates else None,
                        strongest_shot_on_intense_music=hero_on_intense,
                        judged_by=sorted({c.get('judged_by', 'activity heuristic') for c in candidates})),
        craft=dict(ramps=sum(c.speed_profile == 'ramp' for c in timeline.clips),
                   punch_ins=sum(len(c.accents) for c in timeline.clips),
                   blends=sum(b.get('effect') not in (None, 'cut') for b in boundaries),
                   hard_cuts=sum(b.get('effect') == 'cut' for b in boundaries),
                   finishing=validation.get('finishing')),
        delivery=dict(integrated_lufs=integrated, peak_dbfs=peak, width=validation.get('width'),
                      height=validation.get('height'), fps=validation.get('fps')),
    )


def judge(output, metrics, director):
    """Optional rubric grade from Claude using a contact sheet of the finished edit."""
    from .vision_director import image_block, labelled_frame, tile
    timeline, _, _ = _sidecars(output)
    frames = []
    for i, clip in enumerate(timeline.clips[:24]):
        at = clip.start+source_offset((clip.anchor_output if clip.anchor_output is not None else clip.duration/2),
                                      clip.duration, clip.speed_profile)
        frames.append(labelled_frame(clip.source, at, f'{i+1}'))
    stats = json.dumps({k: metrics[k] for k in ('duration', 'shots', 'sync', 'variety', 'highlights', 'craft')})
    content = [{'type': 'text', 'text': 'Measured statistics: '+stats}, image_block(tile(frames, 6))]
    grade, response = director._call(director._request(JUDGE_SYSTEM, JUDGE_SCHEMA, content), 'benchmark grade')
    keys = ('moments', 'variety', 'pacing', 'story', 'overall')
    if not isinstance(grade, dict) or not all(isinstance(grade.get(k), int) and not isinstance(grade.get(k), bool)
                                              and 1 <= grade[k] <= 10 for k in keys):
        raise ValueError('Claude benchmark grade is invalid')
    return dict({k: grade[k] for k in keys}, strengths=str(grade.get('strengths', ''))[:400],
                weaknesses=str(grade.get('weaknesses', ''))[:400], model=getattr(response, 'model', director.model))


def compare(results):
    """Side-by-side headline numbers for several scored montages."""
    rows = []
    for r in results:
        rows.append(dict(output=Path(r['output']).name, on_beat=r['sync']['on_beat'],
                         top_moments_used=r['highlights']['top_moments_used'],
                         non_gameplay_share=r['integrity']['non_gameplay_share'],
                         mean_neighbour_change=r['variety']['mean_neighbour_change'],
                         ramps=r['craft']['ramps'], blends=r['craft']['blends'], lufs=r['delivery']['integrated_lufs'],
                         judge=r.get('judge', {}).get('overall')))
    return rows
