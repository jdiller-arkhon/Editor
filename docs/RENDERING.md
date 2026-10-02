# Rendering quality and transition composition

## Implemented

Decode original sources, retime video/audio, resize with Lanczos, then write lossless FFV1
video (yuv444p) and 24-bit PCM audio in native temporary storage. Lossless body slices and
transition pieces concatenate before **one** final H.264 encode. No intermediate H.264/AAC
generation loss is introduced. Source footage may already contain compression artifacts.

| Quality | H.264 CRF | Encoder preset | Audio |
| --- | --- | --- | --- |
| Draft | 23 | fast | AAC 320 kbps, 48 kHz |
| High (default) | 16 | slow | AAC 320 kbps, 48 kHz |
| Master | 12 | slow | AAC 320 kbps, 48 kHz |

Master is a high-bitrate delivery preset, not a lossless archival/ProRes export. Final video
remains 8-bit yuv420p for broad playback compatibility. Source range/matrix is interpreted
by FFmpeg; the scale filter converts to BT.709 limited range and delivery is tagged BT.709 SDR.
Unknown source metadata relies on FFmpeg defaults; there is no calibrated color pipeline.
Known PQ/HLG HDR input is rejected instead of silently claiming accurate tone mapping.

## Composited transitions

`transitions.py` processes at most two shots per FFmpeg boundary job. Available effects:
- `push`: smooth left push
- `zoom_blend`: zoom-in composite
- `blur`: horizontal blur composite
- `dissolve`: fade between two images
- `cinematic`: deterministic alternating smooth-left, zoom-in, horizontal-blur, smooth-right

Transitions replace the final half-window of shot A and first half-window of shot B.
Held edge frames extend those windows for the two-image blend, avoiding source interval
reuse and keeping output duration and musical cut centers fixed. Handles are not tracked
motion or real extra footage. Window sizes are quantized to frames and capped to one-third
of each adjacent shot so short clips retain visible bodies. Too-short boundaries remain cuts.
Gameplay fades across the boundary; the continuous music bed never restarts there.

Composited pieces and untouched shot bodies remain lossless until delivery encoding.
Boundary time, actual duration, chosen effect and held-handle provenance appear in the
validation report. Timeline settings persist choices for replay. New defaults remain compatible
with older project files. Ollama schema restricts choices to implemented effects.

## Validation and limits

Mandatory generated red/blue fixtures verify simultaneous contribution of both source images
at a transition center, unchanged cut time, four-second total stream coverage, all five blend
styles and high-quality preset metadata. Existing retiming/mixing/duration regression tests remain.
Full export decode, video/audio coverage, dimensions and actual frame rate gate publication.

Source sizes/upscaling are recorded. Upscaling does not recover source detail; increasing output
FPS does not create captured motion. No optical flow, HDR tone mapping, calibrated grading,
subject tracking, GPU encoder certification or perceptual quality benchmark is claimed.
Lossless temporary files can be much larger than delivery files; disk capacity and render time
scale with resolution, length and complexity. Native temporary storage is cleaned after each job.
