# Universal AI Gaming Montage Editor

A local, personal-use gaming montage engine. The first working vertical slice imports gameplay and music, measures activity and musical onsets, builds a deterministic timeline, exports a real MP4 and fully decodes it to validate the result.

## Current status

| Status | Features |
| --- | --- |
| IMPLEMENTED | CLI media import/probing, generic motion/audio activity scoring, non-overlapping clip selection, JSON timeline save/load/replay, CPU H.264/AAC rendering, letterboxing, audio fades, output validation, configuration, hardware/FFmpeg discovery, integration tests |
| EXPERIMENTAL | RMS onset detection and activity-based direction; these are heuristic signals, not semantic game understanding or reliable beat tracking |
| PLANNED | Advanced desktop editing, semantic kills/events, game adapters, learned AI director, reference-style analysis, advanced transitions, speed ramps, original gameplay audio mixing, GPU render validation, Windows installer |

This version provides a command-line engine and an initial desktop workspace; it is not a finished professional editor. It does not yet deliver the artistic judgment of a top montage editor.

## Requirements

Python 3.11+, NumPy 1.24–2.x, FFmpeg and FFprobe on PATH with libx264 and AAC encoding. Windows 10/11 or Linux. No GPU, paid API or downloaded AI model is required. GPU discovery does not validate GPU rendering. Windows execution is not yet tested; Linux CPU rendering is tested. Use adequate disk space for temporary encoded clips and final exports. Analysis decodes low-resolution frames in 30-second chunks; long videos still take time and signal arrays scale with duration.

## Install and run

```sh
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux: source .venv/bin/activate
python -m pip install -e .
montage-editor doctor
montage-editor create --gameplay gameplay.mp4 another.mp4 --music song.wav --output exports/montage.mp4 --duration 30
montage-editor render exports/montage.timeline.json --output exports/revised.mp4
python -m unittest discover -s tests -v
```

Quote paths containing spaces. Install FFmpeg separately and verify `ffmpeg -version` and `ffprobe -version`. `--width`, `--height`, `--fps` customize exports; dimensions must be positive even integers. Inputs must be seekable local files supported by FFmpeg. Output must be a new `.mp4` path. Existing exports and project sidecars are never silently overwritten.

## Editing and exports

The renderer exports H.264 video (CRF 18), AAC music (192 kbps), fixed dimensions and frame rate, preserving source aspect ratio with black bars. Gameplay audio is analyzed when present but excluded from the export. Clips are ordered by activity score and cut near detected music onsets. The engine uses unused source intervals around activity candidates when necessary; requested duration may shorten when footage or music is insufficient. The validation report records shortening.

Outputs include `.timeline.json`, `.analysis.json`, and `.validation.json`. Timelines reference absolute local media paths; they do not embed media or upload it. You can edit a timeline JSON and replay it. Validation checks audio/video streams, dimensions, frame rate, duration and full decode; it does not assess artistic quality or accurately recognized gameplay events.

## Architecture and supported games

`src/montage_editor`: configuration, environment detection, CLI and analysis/director/render pipeline. `tests`: unit and actual FFmpeg render tests. `docs`: architecture, decisions, limitations and session log. `.github/workflows`: mandatory CPU integration CI.

Any game recording with a decodable video stream can use the generic engine. There are no game-specific adapters yet, including Siege. Future adapters will contribute scored event timestamps to the same candidate representation. No game is advertised as having semantic support.

Large assets belong outside Git. Local `assets/`, `models/`, `proxies/`, `cache/` and `exports/` are ignored. Never commit raw gameplay, songs, renders, caches, secrets or virtual environments. Small synthetic fixtures are generated during tests.

See [architecture](docs/ARCHITECTURE.md), [development](docs/DEVELOPMENT.md), [testing](docs/TESTING.md), [roadmap](docs/ROADMAP.md) and [development log](docs/DEVELOPMENT_LOG.md).

## Christian storytelling

The product direction includes contemporary Christian montages that encourage following Christ. `create --story story.json` now supports timed local dialogue recordings, scheduled music ducking, mix limiting, and black/white fade transitions. Dialogue references and original/paraphrase/quotation labels persist in project metadata. These controls are implemented; automated reference selection, scripture captions, narrative AI and studio-quality output remain goals. See [Christian storytelling](docs/CHRISTIAN_STORYTELLING.md) for configuration and creative direction.

## Desktop studio

```sh
python -m pip install -e '.[desktop]'
montage-studio
```

The PySide6 workspace offers native file import, preview/playback/scrubbing, real timeline inspection, editable dialogue cues and references, transition/export settings, background rendering and validated export preview. Dialogue Kind accepts `original`, `paraphrase`, or `quotation`; references are metadata, not captions. “Render loaded timeline” uses stored settings and dialogue; inspector controls apply to new generation. Render progress is indeterminate; there is no cancellation/resume yet. Close is blocked during an export.

Desktop controls are tested offscreen on Linux; physical audio playback and Windows execution remain unvalidated. Qt multimedia codecs/device support may differ from FFmpeg rendering. Advanced reference effects and manual clip editing remain planned. See [reference style brief](docs/REFERENCE_STYLE.md).

![Desktop workspace](docs/ui-preview.png)

Linux desktop dependencies include `libegl1`, `libgl1`, `libopengl0` and `libpulse0` (Ubuntu packages). The desktop CI explicitly installs these; missing `libpulse0` caused the initial desktop run failure. Launch with `montage-studio` or `python -m montage_editor.desktop` after installing the desktop extra. The custom workspace now includes layered surfaces and actual timeline lanes. Timeline seeking applies to the rendered export, not unrendered source sequences.

The desktop now follows the supplied DRIFT visual reference with an original packaged cathedral backdrop, monochrome navigation and five workflow cards. Analyze independently measures gameplay motion/audio and reports candidate activity (not kill confidence). The source library appears after import. AI Director, Color and Styles navigation are disabled until implemented.
