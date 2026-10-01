# Editing and audio quality

## Implemented

The cinematic profile is connected to desktop quick creation and CLI story configuration.
It uses positive log spectral flux at 10 ms hops to identify musical attacks. These are not
validated beats/downbeats. Audio decoding is bounded to 30-second chunks; chunk boundaries
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
