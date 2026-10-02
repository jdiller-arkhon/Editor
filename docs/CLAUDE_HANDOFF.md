# Claude handoff — DRIFT Montage Studio

Prepared 2026-10-02. The repository is the source of truth; read its latest state rather than assuming this document's checkpoint is still HEAD.

## Start here

**Repository:** https://github.com/jdiller-arkhon/Editor

**Development branch:** `feat/working-montage-pipeline`

**Review PR:** https://github.com/jdiller-arkhon/Editor/pull/1

**Default branch at handoff:** `main`, containing the initial foundation. Substantial completed application work is on the development branch, not merged into main.

```sh
git clone https://github.com/jdiller-arkhon/Editor.git
cd Editor
git fetch origin
git checkout feat/working-montage-pipeline
git status
git log -5 --oneline
```

Before this UI/handoff checkpoint, generator upgrade HEAD was `96ef2d6d6915cfd377f3eb287b9290f9e8d77fb6`; its GitHub Actions core/desktop run 36904879432 passed. The new UI/handoff commit is titled **Refine DRIFT workspace and prepare Claude continuation handoff**. Fetch and inspect the actual latest SHA; this document deliberately does not invent its own commit SHA.

Read root CLAUDE.md, README, DEVELOPMENT_LOG, DECISIONS, ARCHITECTURE, RENDERING, EDITING, AI_PIPELINE, TESTING and ROADMAP. Inspect tests before extending the pipeline.

## User intent and current priority

A personal-use, universal gaming montage editor with premium visual design and minimal effort: drop gameplay, choose a local song by title, click Create. It should eventually achieve the creativity and skill of top montage editors, especially the likely reference creator @KaiserEdits, with a contemporary Christian undertone.

The user specifically clarified: **improve the app's automatic montage generation, not merely an exported demonstration**. Prior cathedral/synthesized-tone samples were rejected as white flashes and annoying noise. Real-gameplay test renders exercised mechanics but were never validated as studio/Kaiser-quality edits.

Latest direction: improve UI before moving development to Claude; make the Christian influence **more subtle**. Preserve DRIFT's monochrome depth, quiet purpose/hope/perseverance and optional explicit faith controls. Avoid a dominant cross, prominent religious slogans or an evangelical label on every action.

## Latest UI changes

- Graphite monochrome surfaces, clearer hierarchy, layered film-frame motifs and quiet architecture at 7% opacity. The packaged cathedral resource remains an original generated backdrop, not user footage.
- Neutral branding, “Create montage” and “Creative controls”; no cross glyph in the brand, no large cross in the empty preview. Preview is clearly empty, not fake gameplay.
- Existing working navigation remains; removed disabled planned Color/Styles entries and duplicate workflow strip.
- Creative controls: `Subtle • hope & perseverance` default, `Christian • explicit message`, `Neutral • gameplay focus`. Default closing lines are “Keep the faith.” / “Walk with Christ.” / empty. Users can enter or clear their own line. Switching tone preserves a custom line; QSettings preserves tone/line across sessions.
- The chosen line goes into the actual project/render. Tone supplies the default Ollama brief only when the user has not entered one. This does not add theological understanding to the heuristic engine.
- Main content scrolls at smaller heights; inspector forms use vertically stacked fields. Playback stays disabled until media is selected. Root docs/ui-preview.png is a real offscreen screenshot of the app.
- Existing saved timeline replay uses its stored explicit or subtle message; new defaults must not rewrite old projects.

## Implemented application

**Core:** Python 3.11+, NumPy, FFmpeg/FFprobe; optional PySide6 desktop. CLI entrypoints `montage-editor`, `montage-studio`; package version 0.1.0.

- Media probing/import, generic motion/audio activity candidate scoring; no game-specific semantics.
- Musical attack detection: positive log spectral flux at 10 ms hops. Energy is sampled at 50 ms. Since 2026-10-02 (Claude session) `rhythm.py` adds a measured beat grid (tempo, beats, 4/4 downbeat phase, phrase marks, confidence) used for beat-aligned cut planning when confident; see EDITING.md and DEVELOPMENT_LOG.
- Optional energetic excerpt selection from the chosen local song, based on energy/variation. `music_start` is used consistently for analysis, audio rendering and project replay. Local title matching scans filenames only; no streaming/downloading service.
- Deterministic unused-interval selection. Try all genuine anchored candidates before fallback intervals; never silently reuse footage to fill requested duration. Source/music limits can shorten the result; the report says so.
- Cinematic activity build/resolve ordering and source diversity. Exact candidate source/output anchors persisted only when achievable.
- Piecewise 1.4× / 0.6× / 1.4× retiming; source consumed equals output duration, audio uses atempo. These are stepped ramps, not smooth curves/optical flow.
- Actual two-image push, zoom-in, horizontal-blur and dissolve composites. Cinematic mode alternates directions/effects. Bounded pair jobs replace each cut neighbourhood; held edge frames supply handles. Musical cut centers and total duration remain fixed. Brief held handles may look frozen.
- Lossless FFV1 yuv444p / 24-bit PCM intermediate processing in native temporary storage; one lossy H.264 delivery encode. High CRF 16 / slow, Master CRF 12 / slow, Draft CRF 23 / fast; AAC 320 kbps / 48 kHz.
- Lanczos resizing, BT.709 SDR conversion/tags, source-size/upscaling metadata. Known PQ/HLG HDR rejected pending tone mapping. Master is not a lossless archival/ProRes format. Unknown color metadata relies on FFmpeg defaults.
- Gameplay audio mix, continuous music, timed local dialogue with provenance, narration-driven music sidechain ducking, measured two-pass loudnorm and limiter. Literal closing text via drawtext textfile with expansion disabled.
- Timeline JSON roundtrip/replay, analysis/validation sidecars; absolute paths reference local media, not embedded assets.
- Output validation: independent video/audio durations, dimensions, actual FPS, full decode. Publish only validated exports and refuse existing outputs/sidecars.

**Desktop:** native drag/drop, source import, local song matching and ambiguity choice, background jobs, actual media playback/scrubbing, real timeline lanes/table, story/audio/quality controls and validated export preview. Simple mode defaults to 1080p/High/cinematic blends/mastering/automatic song excerpt. Advanced settings hidden initially. Outputs get unique names in OS Movies/Videos/DRIFT. No job cancellation or granular progress; close is blocked during a job.

**Ollama (experimental):** loopback structured `/api/chat`, anonymous activity metadata only, maximum 120 candidates. Validated IDs/pacing/transitions. No model-generated commands or paths. No visual frames, semantic kills, TTS or autonomous reference selection. Live Ollama is absent/unvalidated; tests use transport mocks followed by actual rendering. No automatic model download. Proxy bypass and redirect refusal are intentional.

## Status boundaries

IMPLEMENTED tools are connected and exercised by tests. EXPERIMENTAL: activity-based creativity, attack tracking, energetic excerpt selection, metadata-driven local AI planning and qualitative transition quality. PLANNED: semantic game events/adapters, phrase/downbeat evidence, smooth high-frame-rate-aware ramps, optional optical flow, subject tracking, calibrated grading/HDR, intelligent sound effect selection, verified scripture/reference selection, captions/TTS, story evaluation, cancellable/resumable jobs, Windows installer and GPU validation.

Universal support means decodable recordings from any game; it does not mean semantic recognition for Siege/Destiny or every game. Kaiser primary project-store references suggested After Effects, but playback was unavailable; there was no rigorous frame-level style study. Do not invent a plugin/effect inventory.

## Module map

| File | Responsibility |
| --- | --- |
| src/montage_editor/desktop.py | PySide6 workspace, jobs, quick-create defaults, preferences, story tones |
| workspace_widgets.py | Code-native banner/preview and actual-data timeline drawing |
| pipeline.py | Probe/analyze/direct/render, models, validation and publication |
| editing.py | Output-to-source retime mapping and filters |
| transitions.py | Bounded two-shot lossless transition composition |
| music_sections.py | Deterministic energetic local-song excerpt |
| music_library.py | Local filename matching and ambiguity |
| ai_director.py | Ollama transport/schema/plan validation |
| storytelling.py | DialogueCue and provenance/bounds |
| config.py / environment.py / cli.py | Settings, discovery, CLI |
| tests/test_*.py | Mandatory core/media integration tests |
| tests/desktop_checks.py | Separate offscreen desktop checks |
| .github/workflows/ci.yml | CPU and desktop CI |

## Setup and verification

Install FFmpeg/FFprobe separately, with libx264, FFV1, PCM/AAC encoding and xfade/drawtext/loudnorm filters.

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[desktop]'
montage-editor doctor
montage-studio
# Alternatively desktop: python -m montage_editor.desktop
python -m unittest discover -s tests -v
```

Linux desktop system libraries: libegl1, libgl1, libopengl0, libpulse0. CI installs these. Offscreen:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests -p desktop_checks.py -v
```

Windows PowerShell offscreen environment syntax differs (`$env:QT_QPA_PLATFORM='offscreen'`, `$env:PYTHONPATH='src'`). Windows/device playback is not validated here. PipeWire/PulseAudio socket warnings are expected headlessly and are not proof of audible playback validation.

Last UI session baseline: 14 core tests passed in 44.504 seconds; final UI checks cover six desktop tests including tone selection, custom closing-line preservation, real quick-create settings, background errors and import persistence. Read DEVELOPMENT_LOG for final timings/CI.

Important regressions that must stay fixed:
1. Place accurate input seek before `-i`; output seeking previously truncated video while container/audio duration appeared correct.
2. Independently validate video AND audio coverage. A container-only duration check accepted a broken sample.
3. Quantize directed cuts to whole frames and give concat explicit shot durations; many fractional shots need real regression renders.
4. Encode seek-dependent MP4/muxer outputs in native temp storage. Workspace-backed random writes produced missing moov/truncated files. Sequentially copy validated output into a destination staging file, flush/fsync, hard-link without overwriting, remove stage.
5. Keep FFmpeg measurement at info log level when parsing loudnorm JSON; error-only logging suppressed results.
6. Retain compatible PCM/silent audio for every intermediate so silent and audio sources concatenate correctly.
7. Never overwrite a user's custom closing line during tone restore or switching.

Core integration tests generate small media at runtime and fully decode exports. Composite red/blue fixtures establish both source images at the cut. A two-frequency music fixture confirms selected source offset in actual rendered audio. The sixteen-shot fractional-duration render guards concat timing. Desktop quick-create checks actual generator arguments. Never weaken checks just to get a pass.

## Recommended next work

1. Establish an editorial benchmark with real user footage and licensed desired music. Compare candidate quality, event-to-beat timing, shot diversity and transition choices, not file count or image sharpness alone.
2. Add semantic event evidence (game adapter/OCR/local vision as appropriate) with truthful confidence; retain generic fallback. Pair it with musical phrase/downbeat analysis and user corrections.
3. Smooth speed curves with source-FPS-aware slowdown, optional validated interpolation, meaningful effect selection and real transition handles rather than hold frames.
4. Narration/caption/reference planning with exact provenance and subtle/explicit user tone. No fabricated quotations or voices attributed to real people.
5. Resource controls/cancellation/progress, Windows execution/installer, then GPU and live Ollama benchmarks.

Preserve existing working editing/rendering instead of replacing it with extensive documentation/scaffolding. Document significant decisions and tested vs planned functionality. Commit/push meaningful verified checkpoints to this repository.

## Claude kickoff prompt

Continue my DRIFT Universal AI Gaming Montage Editor in https://github.com/jdiller-arkhon/Editor on feat/working-montage-pipeline (PR #1). Read CLAUDE.md and docs/CLAUDE_HANDOFF.md, fetch the current repository, inspect the development log and run the core and desktop tests before changing anything. Keep the refined monochrome UI and subtle Christian influence with explicit faith available in Creative controls. Focus on the quality of montages the app automatically generates, not on polishing a demonstration clip. Preserve the working pipeline and regression safeguards. Report actual starting state, implemented/experimental/planned boundaries and your next concrete engineering priority; then proceed with meaningful tested improvements and push them to the same repository.
