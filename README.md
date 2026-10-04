# Universal AI Gaming Montage Editor

A local, personal-use gaming montage engine. The first working vertical slice imports gameplay and music, measures activity and musical onsets, builds a deterministic timeline, exports a real MP4 and fully decodes it to validate the result.

Continue this project in Claude using [CLAUDE.md](CLAUDE.md) and the detailed [handoff](docs/CLAUDE_HANDOFF.md). The working application currently lives on `feat/working-montage-pipeline` in [PR #1](https://github.com/jdiller-arkhon/Editor/pull/1); `main` contains the initial foundation. Verify branch state before continuing.

## Current status

| Status | Features |
| --- | --- |
| IMPLEMENTED | CLI media import/probing, generic motion/audio activity scoring, non-overlapping clip selection, JSON timeline save/load/replay, lossless intermediate processing and single-delivery-encode H.264/AAC rendering, letterboxing, audio fades, gameplay mixing, measured two-pass loudness normalization, narration sidechain ducking, restrained zoom transitions, piecewise speed ramps, output validation, configuration, hardware/FFmpeg discovery, integration tests |
| IMPLEMENTED | Add music from a YouTube video or Spotify track link (`[links]` extra / yt-dlp; desktop “Add from link”, CLI `add-music`). Spotify audio is never downloaded: a matching local file is used, else the YouTube match whose measured duration agrees with Spotify’s. Live YouTube unvalidated here (bot-checked) |
| EXPERIMENTAL | Non-gameplay exclusion from learned HUD presence (deaths, scoreboards, menus, loading), gameplay audio transients in scoring, hero placement of the strongest moments on the most intense music. Calibrated on one game |
| EXPERIMENTAL | Opt-in Claude vision editor (`--claude-editor`): Claude reviews sampled frames of candidate moments, scores highlights, flags menus/loading screens and suggests story order; local engine keeps all timing. Mock-tested only; live quality unvalidated |
| EXPERIMENTAL | Measured beat grid (tempo, beats, 4/4 downbeat phase, four-bar/energy-change phrase marks, confidence) driving beat-aligned cuts, with spectral-flux attack pacing as the fallback; activity-based pacing/peak alignment. These are signal heuristics, not semantic game or song-structure understanding |
| PLANNED | Advanced desktop editing, semantic kills/events, game adapters, learned AI director, reference-style analysis, optical-flow transitions, smooth velocity curves, semantic sound design, GPU render validation, Windows installer |

This version provides a command-line engine and an initial desktop workspace; it is not a finished professional editor. It does not yet deliver the artistic judgment of a top montage editor.

## Requirements

Python 3.11+, NumPy 1.24–2.x, FFmpeg and FFprobe on PATH with libx264, FFV1, PCM and AAC encoding, plus xfade, drawtext and loudnorm filters. Windows 10/11 or Linux. No GPU, paid API or downloaded AI model is required. GPU discovery does not validate GPU rendering. Windows execution is not yet tested; Linux CPU rendering is tested. Use adequate disk space for temporary encoded clips and final exports. Analysis decodes low-resolution frames in 30-second chunks; long videos still take time and signal arrays scale with duration.

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

The renderer exports H.264 video (High: CRF 16 / slow; Master: CRF 12 / slow; Draft: CRF 23 / fast), AAC music (320 kbps), fixed dimensions and frame rate, preserving source aspect ratio with black bars. Gameplay audio is analyzed and can be mixed at a configurable gain. Simple mode uses 25% gameplay and 80% music before measured two-pass mastering toward −16 LUFS / −1.5 dBTP and a peak limiter. Narration ducks the music with attack/release smoothing. When the song has a confident steady beat, cuts land on tracked beats chosen by a global path that favours downbeats, phrase boundaries and 2/4/8/16-beat shots, with shorter shots in louder passages; otherwise clips cut near detected musical attacks. Activity peaks align to an interior (down)beat inside shots where source bounds permit. The automatic song excerpt starts on a measured phrase/downbeat when the beat grid is confident. The validation report's `music_alignment` records the pacing mode and measured cut-to-beat/downbeat/phrase alignment. The engine uses unused source intervals around activity candidates when necessary; requested duration may shorten when footage or music is insufficient. The validation report records shortening.

Outputs include `.timeline.json`, `.analysis.json`, and `.validation.json`. Timelines reference absolute local media paths; they do not embed media or upload it. You can edit a timeline JSON and replay it. Validation checks audio/video streams, dimensions, frame rate, duration and full decode; it does not assess artistic quality or accurately recognized gameplay events.

## Architecture and supported games

`src/montage_editor`: configuration, environment detection, CLI and analysis/director/render pipeline. `tests`: unit and actual FFmpeg render tests. `docs`: architecture, decisions, limitations and session log. `.github/workflows`: mandatory CPU integration CI.

Any game recording with a decodable video stream can use the generic engine. There are no game-specific adapters yet, including Siege. Future adapters will contribute scored event timestamps to the same candidate representation. No game is advertised as having semantic support.

Large assets belong outside Git. Local `assets/`, `models/`, `proxies/`, `cache/` and `exports/` are ignored. Never commit raw gameplay, songs, renders, caches, secrets or virtual environments. Small synthetic fixtures are generated during tests.

See [architecture](docs/ARCHITECTURE.md), [development](docs/DEVELOPMENT.md), [testing](docs/TESTING.md), [roadmap](docs/ROADMAP.md) and [development log](docs/DEVELOPMENT_LOG.md).

## Christian storytelling

The product direction includes contemporary Christian montages that encourage following Christ. `create --story story.json` now supports timed local dialogue recordings, signal-driven music ducking, mix limiting, and black/white fades and cinematic composited transitions. Dialogue references and original/paraphrase/quotation labels persist in project metadata. These controls are implemented; automated reference selection, scripture captions, narrative AI and studio-quality output remain goals. See [Christian storytelling](docs/CHRISTIAN_STORYTELLING.md) for configuration and creative direction.

## Desktop studio

```sh
python -m pip install -e '.[desktop]'
montage-studio
```

The PySide6 workspace offers native file import, preview/playback/scrubbing, real timeline inspection, editable dialogue cues and references, transition/export settings, background rendering and validated export preview. Dialogue Kind accepts `original`, `paraphrase`, or `quotation`; references are metadata, not captions. “Render loaded timeline” uses stored settings and dialogue; inspector controls apply to new generation. Render progress is indeterminate; there is no cancellation/resume yet. Close is blocked during an export.

Desktop controls are tested offscreen on Linux; physical audio playback and Windows execution remain unvalidated. Qt multimedia codecs/device support may differ from FFmpeg rendering. Advanced reference effects and manual clip editing remain planned. See [reference style brief](docs/REFERENCE_STYLE.md).

![Desktop workspace](docs/ui-preview.png)

Linux desktop dependencies include `libegl1`, `libgl1`, `libopengl0` and `libpulse0` (Ubuntu packages). The desktop CI explicitly installs these; missing `libpulse0` caused the initial desktop run failure. Launch with `montage-studio` or `python -m montage_editor.desktop` after installing the desktop extra. The custom workspace now includes layered surfaces and actual timeline lanes. Timeline seeking applies to the rendered export, not unrendered source sequences.

The desktop uses layered graphite panels, restrained architectural texture, clear media intake and a real preview/timeline. Creative controls are hidden until needed. Analyze independently measures gameplay motion/audio and reports candidate activity (not kill confidence). The source library appears after import. AI Director opens local director settings.

## AI director on your computer (Ollama, default)

The default director runs a **local vision model in [Ollama](https://ollama.com/download)**: frames of your footage never leave the computer (loopback only, no proxy, no redirects). In the desktop choose **AI director → Local AI director** (the default), press **Set up local AI** once (checks Ollama and downloads the model through it with progress and cancel), then Create. CLI: `create --director auto|local|claude|activity --local-model qwen2.5vl:7b`; `doctor` reports whether Ollama is running and which installed models can see images.

The local model watches six-frame strips of candidate moments and answers a **checklist** per strip (which frames are covered by a scoreboard/menu, is an opponent visible, is there gunfire or explosions, does an opponent die, the peak frame, a highlight score); the engine turns those answers into judgements. It then assigns moments, slow motion, punch-ins and transitions to the beat slots and reviews the cut. The engine **enforces an editing playbook** whatever the model says: a strong opener, the strongest moment on the drop, hard cuts on the beat with transitions only into a new phrase/build/drop, dissolve only into the final shot, slow motion in at most one shot in four and never back to back, no punch-ins on calm music, and a clean final shot. Directional pushes follow the measured camera pan, slow-motion hits get impact frames, and loud downbeats get beat FX.

Measured on 16 hand-labelled strips from a held-out Xonotic duel (CPU only, so speeds are slow; a GPU is much faster):

| Model (checklist prompt) | Death screens caught | False flags | Fight vs walking (AUC) | Per strip |
|---|---|---|---|---|
| **qwen3.5:9b** (default) | 4/5 | 0 | 0.70 | 43 s |
| qwen2.5vl:7b (previous default) | 0/5 | 0 | 0.70 | 89 s |
| gemma4:e4b | 5/5 | 11 | 0.37 | 25 s |
| activity heuristic alone | — | — | 0.63 | — |

The same qwen3.5:9b with the earlier single-judgement prompt caught 1/5 death screens (AUC 0.58), which is why the checklist exists. Local judgements are blended 60/40 with the measured activity score, and if a model marks more than two-thirds of the clips as overlays (as gemma4:e4b did) its flags are ignored rather than deleting footage. Larger models (qwen3.5:27b and newer) were not measured here. Claude (cloud, opt-in) remains available under the same menu; the activity engine needs no AI at all.

## Output and delivery

- **Every format from one edit**: *Export every format* (or `render TIMELINE --output X --formats youtube-1080p30,shorts-1080x1920,instagram-1080x1350`) delivers the same cut as 16:9, 9:16 and 4:5 with action-following crops, each fully decoded and validated.
- **Platform loudness**: automatic montages master to −14 LUFS (`target_lufs`), the level YouTube, TikTok and Instagram normalise to; older timelines keep −16.
- **Beat FX**: on drops and downbeats in the loudest quarter of the song, an exposure pulse, a three-frame RGB split and a shake (`pulses`, default empty).
- **Kinetic closing title** and a **Film** look (cinematic grade with fine grain).
- **Speed**: independent FFmpeg work (shot renders, transition handles, blends, colour statistics, gameplay analysis) runs concurrently, one job per core up to 8 (`DRIFT_WORKERS` overrides), hard-cut shots are no longer re-encoded before assembly, and the final H.264 encode uses every core. On the 4-core development machine the same 30 s 1080p montage of two real Xonotic sources went from 569 s to 276 s with an identical timeline; parallel analysis is tested identical to sequential.

## Director chat

The **Director chat** panel lets you talk to the director in plain words. It answers and changes the edit only through validated actions that drive the same controls you see:

- settings: pace, length, look, tone, closing line, brief, song (any link, path or title), export format, slow motion, swishes, motion blur, beat FX;
- **styles**: "make it hype" (fast, punchy, beat FX), "cinematic" (film grade, smooth slow motion), "chill" (calm, clean) or "raw" (fast, no effects);
- **single shots**: "slow motion on shot 4", "punch-ins on shot 2", "dissolve out of shot 5", "swap shot 3", "move shot 2 later";
- **renders**: quick preview, full montage, final from the preview, render the edited timeline, or deliver every platform format.

It knows each shot's start time, length, treatment, outgoing transition, musical marks (drop/build) and judged event, so it can explain the edit ("why open with that shot?"). When you ask for feedback it also sees a contact sheet of the shots. Unknown values, impossible shots and **actions on topics you did not mention are rejected and shown**, and **explicit values in your words win** over the model's paraphrase (a number of seconds, a pasted link, a named look, pace or style).

Measured with qwen3.5:9b on 16 scripted requests (CPU): before these changes 11/12 everyday requests and 0/4 of the new abilities; with worked examples in the prompt the new abilities went to 4/4 but three everyday requests regressed (a garbled length, a dropped link, "film" read as "cinematic"); grounding to the person's words fixed those. On a larger set of 24 requests (adding 8 harder combined or negated ones), two clean runs scored 24/24 at ~31 s per request; it is a small scripted set, not a guarantee.

## Simple mode: drop, song, create

1. Drop gameplay clips anywhere in the desktop window (or use Import).
2. Put **any song** in the one song box: paste a YouTube or Spotify track link, paste a file path (audio, or a video with sound), drop the file, or type a title from your music folder. Links download into `Music/DRIFT` (no folder prompt) and creation continues automatically.
3. Click **Create montage**. DRIFT analyzes, directs, renders, validates and automatically saves a uniquely named MP4 under your system Videos/Movies folder in `DRIFT`.

Typed titles match local filenames (including artist/title words) in your music folder and `Music/DRIFT`; only pasted links download. Ambiguous matches offer a choice. Rename local music files descriptively. Matching is bounded to 10,000 folder entries; choose a focused music folder. Clip duplicates are ignored. Video/audio media validity is checked by the rendering engine after import.

**Pace** (calm 2–5 s, balanced 1.5–4 s, fast 1–3 s, hyper 0.75–2.25 s shots before beat snapping; CLI `--pace`) sits beside the export preset. Advanced controls are hidden by default; director, model, pace, brief and music folder are remembered locally. The default Subtle tone emphasizes hope and perseverance with an editable original closing title, “Keep the faith.” Creative controls also offer an explicit Christian tone (“Walk with Christ.”) and Neutral tone without a default title. Custom closing lines persist across tone changes and restarts; clear the field to omit the title. It does not automatically generate spoken scripture or reference dialogue. Title rendering requires FFmpeg drawtext and an available font; Windows validation remains outstanding.

Kaiser-level creativity remains a development goal, not an implemented quality guarantee. Semantic visual analysis, smooth speed curves/subject-aware compositing, narration generation and iterative editorial evaluation are still needed.

## Cinematic edit profile

Simple mode enables restrained center zooms, occasional piecewise fast–slow–fast retiming,
source diversity and an activity-based build/resolve sequence. It keeps musical cut times fixed,
never repeats used footage and preserves pitch with `atempo` for gameplay audio. A quiet source
gets an explicit silent gameplay track while the real imported soundtrack remains audible.
Silent music is rejected. Timeline fields persist effects, mix gains and exact activity anchors.

CLI story JSON can opt in with `"edit_profile":"cinematic"`, `"transition":"zoom"`,
`"gameplay_gain":0.25`, `"music_gain":0.8`, `"normalize_audio":true`.
See [editing and audio](docs/EDITING.md) for constraints and quality checks.
These are tested editing tools, not verified studio-quality creative judgment.

## Composited transitions and export quality

Simple mode now defaults to Full HD and a cinematic mix of smooth pushes, zoom blends,
blur blends and directional transitions. Advanced controls offer each effect individually
plus dissolve. These actually blend two images around the existing cut; musical cut times
and total duration remain fixed. Brief held-frame handles avoid consuming extra source footage.

FFV1/PCM intermediates are lossless; one final H.264 encode uses the selected quality preset.
Lanczos resizing and BT.709 SDR delivery metadata are explicit. Known HDR sources are rejected
until tone mapping is implemented. Source size and upscaling are recorded in validation metadata:
1080p delivery of a smaller source cannot create native 1080p detail.
CLI supports `--quality high`, `--quality master` or `--quality draft`.
Lossless processing needs more temporary storage and CPU time. See [rendering](docs/RENDERING.md).

Quick-create can automatically choose an energetic excerpt of your selected local song.
The Advanced checkbox disables this when you want the original opening. Song selection remains
local filename matching; no songs are downloaded. The excerpt algorithm measures energy and
variation, not lyrical meaning or musical phrases. Its source offset persists in projects.

## Workflow (desktop)

Pick **Export for** (YouTube, Shorts/TikTok, Instagram, or Custom), then **Create montage**, or **Quick preview**
for a fast draft and **Render final from preview** for the identical edit at full quality. Progress shows each
stage; **Cancel** stops immediately and saves nothing. After a render, select a shot in the timeline to move it
or swap it for another analysed moment, then **Render loaded timeline**. Creative controls hold tempo correction
(Tap tempo), look, slow-motion quality, motion blur and transition swishes.
