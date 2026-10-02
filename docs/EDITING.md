# Editing and audio quality

## Implemented

The cinematic profile is connected to desktop quick creation and CLI story configuration.
It uses positive log spectral flux at 10 ms hops to identify musical attacks, compensated for
the 32 ms half-window plus one hop of analysis latency (calibrated on synthetic click tracks).

### Beat grid and beat-aligned cuts (experimental)

`rhythm.py` measures tempo (autocorrelation, 60–200 BPM, octave prior around 120), beats
(dynamic programming), a 4/4 downbeat phase (strongest <200 Hz accents) and phrase marks:
`grid` every four bars from the first downbeat (an assumption, labelled as such) and `rise`/`fall`
where a bar's energy departs from the previous two bars. Confidence combines autocorrelation
periodicity, the share of beats on strong attacks and interval steadiness; below 0.5 the
original attack pacing is used and the sidecar says so (`cut_mode`).

With a usable grid the director solves a global path over beats: shots end on beats (or the
programme end), downbeats and phrase boundaries are rewarded, 2/4/8/16-beat shots get a small
bonus, running across a phrase boundary is penalised, and the target length moves from
`maximum_clip` toward `minimum_clip` as 1 s-smoothed song energy rises. If clip bounds cannot be
met from the grid the attack planner is used instead. Activity peaks anchor on an interior
downbeat (else beat) near the shot centre. Cinematic impact ramps go on shots starting at a
measured lift or a loud four-bar boundary, never twice in a row; desired candidate activity
follows song intensity, calmer at the end for the closing line. The automatic excerpt starts on
a phrase mark/downbeat of the whole song when its grid is confident.

### Editing craft in beat mode (cinematic profile)

- **Smooth speed ramps** (`ramp` profile): speed follows 1 + 0.5·cos(2πt/D), easing from 1.5× at the
  shot edges to 0.5× at its centre, sampled at 16 piecewise-linear knots and rendered with a single
  inverted `setpts` mapping (audio: 16 `atempo` pieces). Source consumed equals output duration and
  anchors use the exact rendered mapping. Placed on shots starting at measured lifts or loud phrase
  turns, never twice in a row. Frames are duplicated, not interpolated: 0.5× of 30 fps footage holds
  each frame twice; 60 fps sources stay fluid. The legacy stepped `impact` profile remains for
  attack-mode edits and saved projects.
- **Beat punch-ins** (`Clip.accents`): on loud, real-time shots a +7% punch-in with a small decaying
  shake starts on interior downbeats, or the mid-bar beat of one-bar shots, and decays to exactly
  zoom 1 within 0.6 s (zoompan is only an identity at exactly 1; a never-quite-zero exponential
  softened every later frame).
- **Per-cut transitions** (`Timeline.boundary_transitions`): ordinary beats are hard cuts; a measured
  lift gets a zoom-through, four-bar turns alternate left/right pushes, energy falls dissolve. Only
  applied when the user's style is `cinematic` and beat pacing was used; other styles stay uniform.
- **Excerpt grid**: an automatic excerpt inherits the whole-song beat/bar/phrase grid and energy scale
  (shifted), so bar numbering and "how loud is this" are judged against the whole song.

Both new fields default to empty, so older timelines load and replay unchanged.

The validation report's `music_alignment` gives the pacing mode, tempo, confidence and the
share of cuts on beats/downbeats/attacks plus phrase boundaries cut. Tests use decoded
synthetic tracks with known ground truth (≤20 ms beat error at 90/128/150 BPM, correct
downbeat phase, lift detected, white noise rejected). Real music with rubato, swing,
tempo changes, half-time drops or non-4/4 meter is unvalidated; there is no user-correction UI yet. Audio decoding is bounded to 30-second chunks; chunk boundaries
can introduce false attacks. Energy analysis remains available for inspection.

Cuts remain on the output clock. Within each shot the director tries to place an activity
peak on an interior attack; the timeline records both source and output anchors only when
alignment is possible. Source bounds and unused footage take priority. Activity reflects
motion/loudness, not kills. Heuristic cinematic ordering encourages different sources and
an opening/build/resolve activity arc; Ollama's explicit ranking takes precedence.

Occasional impact shots use three piecewise speeds: 1.4×, 0.6×, 1.4×, occupying 25%, 50%,
25% of output time. Total source consumption equals output duration. Audio uses pitch-preserving
atempo. These are stepped ramps, not smooth velocity curves. Slowed low-frame-rate input can
judder; no optical flow is claimed. A bounded 6% centered zoom at shot edges is a motion treatment,
not a blended transition. Its decay follows transition_duration. Black/white fades remain optional.
Separate composited transitions (`cinematic`, `push`, `zoom_blend`, `blur`, `dissolve`)
now replace each cut neighbourhood with two-image blends using held-frame edge handles.
The cut stays at the same musical time, and total duration is preserved.

All intermediate shots retain audio, or a stereo silent track for silent video inputs.
Music and gameplay gains are independently configurable in [0,2]. Narration is mixed from
local recordings; its real signal drives music sidechain compression (15 ms attack, 250 ms
release). No synthetic noises or narration are injected automatically. Quick mode retains
the Christian closing message; it does not generate or authenticate scripture quotations.

Optional mastering measures the actual mix first, then supplies those measurements to FFmpeg
loudnorm targeting −16 LUFS, −1.5 dBTP and LRA 11. FFmpeg may use dynamic normalization when
linear requirements cannot be met. A peak limiter and 48 kHz output follow. AAC encoding can
change true peaks; this is not a certified broadcast delivery check. Silent selected music is
rejected. Full decode and independent audio/video duration checks gate publication.

## Automated verification

Mandatory generated-media integration tests render/replay the real pipeline, retime footage,
apply motion zoom, mix gameplay/music, master and decode. Frame differences establish visible
changes; RMS/peak bounds and a frequency check establish an audible retained soundtrack.
Unit tests verify retimed source consumption, exact anchor mapping, invalid gains and unused
source intervals. Dialogue/fade tests are retained. These checks run without a GPU.

## Remaining gaps

Semantic event recognition, manually authored event markers, tracked subject motion,
optical-flow retiming, smooth velocity curves, color management/grading, sound effect selection,
automated reference/narration selection, theology review and reference-style visual evaluation
remain unimplemented. Real gameplay, licensed music and narration should be evaluated together
before claiming professional artistic quality. Generated test patterns test mechanics only.


### Non-gameplay exclusion, audio transients and hero placement (implemented)

- **HUD presence** (`screen_analysis.py`): persistent HUD edges are learned from the footage's keyframes
  (pixels that are an edge in ≥60% of samples). Each analysis frame's HUD presence is measured relative
  to the median; below 0.35 the span is excluded (padded 0.5 s) and reserved so no shot or fallback fill
  covers it, between 0.35 and 0.6 the score ramps down. Footage with no stable HUD (<120 mask pixels)
  is never excluded. Calibrated on a hand-labelled Xonotic duel (CC BY-SA 4.0): 4 min train + 5 min
  held-out. All death/scoreboard spans were found in both; at the training-chosen threshold 0.5 the
  held-out clip also had 3 short respawn-HUD false spans; 0.35 (chosen after seeing held-out data, so
  not independently validated) removed them. Hand labels at 2 s spacing missed two scoreboard spans
  the detector found. One game only; other games' HUDs are unmeasured.
- **Audio transients**: broadband positive spectral flux of gameplay audio (gunshots, explosions, impacts)
  now contributes 25% of a candidate's activity score (motion 55%, loudness 20%). Loud ≠ kill.
- **Hero placement**: in cinematic heuristic edits the top 1–3 moments are reserved for the most intense
  music segments, so the best moment always makes the cut on the loudest part of the song. A moment
  at a source edge that cannot be exactly beat-anchored is still used if it sits inside the shot.
