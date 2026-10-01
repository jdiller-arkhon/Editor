# Development log

## 2026-10-01 — Foundation
- Starting state: public empty repository; GitHub default main; no remote branches, commits, files or issues.
- Objective: establish reviewable package, configuration, environment discovery and CI.
- Added package, unittest suite, build metadata, ignored local assets, README and architecture documentation.
- Decision: Python + FFmpeg + NumPy; no mandatory GPU/model service. unittest avoids an extra test dependency.
- Validation: see checkpoint commit; local clean virtual environment tests and doctor executed before commit.
- Limitations: no editing pipeline or UI yet. Next priority: tested actual end-to-end render.

## 2026-10-01 — First working vertical slice
- Objective: import → analyze → candidate moments → music onsets → timeline → real MP4 → output validation.
- Added pipeline and CLI create/render commands, timeline persistence, non-overlap direction, chunked motion/audio analysis, letterboxed CPU rendering and full-decode validation.
- Added mandatory generated-media integration test, timeline unit tests and detailed status/development/architecture/roadmap documentation.
- Initial integration exposed premature shortening from overlapping peak windows; director now searches unused intervals around candidate moments. All five tests subsequently passed, including six-second export and timeline replay.
- Baseline tests: two passed in a fresh venv using system dependencies; this was isolated package installation, not fully isolated dependencies. Further clean-environment verification recorded below.
- No performance benchmark or real gameplay editorial evaluation performed. Synthetic output only; no GPU/Windows validation.
- Git shell push had no credentials; publish via connected GitHub API, then verify remote refs. Never claim the original local commit was pushed when API commit SHAs differ.
- Next priority: real-gameplay quality evaluation and preview/manual control. Desktop UI, semantic AI, GPU execution and installer remain planned.
- Clean environment: fresh venv without system packages, built/installed project wheel with freshly downloaded NumPy 2.5.3; all five tests passed in 4.158 seconds. FFmpeg remains a separately installed system executable.
- Foundation GitHub commit: c25a568521a0978b063e788467d14e639cebcb07 (main).

## 2026-10-01 — Christian storytelling controls
- User goal: studio-quality montages/videos with a deep Christian undertone that inspire following Christ.
- Implemented optional story JSON import, timed local dialogue cues, source-bound checks, scheduled music ducking, output limiter and black/white clip fades. Persisted cues and provenance metadata with backward-compatible timelines.
- Added creative direction and explicit separation of original narration, paraphrases and quotations. No supplied reference audio, voice generation, verse verification or automatic theological direction.
- Tests: mandatory generated-media render expanded to dialogue/fade render, replay serialization, invalid cue bounds and opening black-frame check; normal pipeline tests retained.
- Remaining: real gameplay/narration quality evaluation, captions, intelligent narrative planning and desktop preview. Studio quality is an aspiration, not validated status.
- Validation result: all five tests passed in 6.509 seconds; compileall passed.

## 2026-10-01 — Reference research and desktop workspace
- User requested Kaiser-style editing techniques with Christian flair, then a premium detailed UI.
- Identified likely @KaiserEdits using primary channel/project-store sources. Project store confirms After Effects; playback unavailable. Provisional skill roadmap written in REFERENCE_STYLE.md; no claimed frame-level study or plugin inventory.
- Added optional PySide6 desktop entry point with native imports, Qt multimedia preview/playback, actual timeline table, dialogue cue/provenance editing, export settings, background RenderJob, error display and validated output preview.
- Added separate desktop CI job. Two desktop checks passed offscreen; five core/render tests passed in 13.330 seconds. Screenshot inspected and included in docs. Compile/import integrity checked.
- Offscreen environment reports unavailable PipeWire/PulseAudio devices; audible playback not validated. Windows remains untested. No cancel/resume, manual clip editing, captions or advanced motion/speed effects yet. Loaded-timeline replay uses stored controls, not inspector edits.
- Next: obtain accessible local reference clips for precise style breakdown, test desktop with real footage/audio on Windows, then implement measured timing/speed/transition controls.

## 2026-10-01 — Custom depth and CI repair
- Investigated failed GitHub run 36879866047: core test job passed; desktop import failed because libpulse.so.0 was missing. Added libpulse0 to Linux desktop CI dependencies; retained mandatory multimedia tests.
- Added code-native cinematic light/cross canvas, concentric depth details, gradient panel surfaces, soft shadows and raised controls. No generated fake footage.
- Added actual video/music/dialogue timeline lanes with time ruler and export seek. Empty lanes are clearly empty; no fabricated waveform or events. Added module launch support (`python -m montage_editor.desktop`).
- Offscreen desktop tests pass; refreshed screenshot inspected. Audible playback and Windows remain unvalidated.

## 2026-10-01 — User-supplied DRIFT reference redesign
- Read uploaded image(5).png directly from scratch. Adopted DRIFT branding, left navigation, cathedral/cross hero, monochrome raised surfaces, five workflow cards, wide preview and scene/story inspector.
- Generated original cathedral backdrop using built-in image generation with the user's image as style/composition reference, not an edit target. Packaged compressed resource at src/montage_editor/resources/cathedral.jpg; user reference itself is not committed.
- Implemented separate background Analyze action returning real motion/audio candidates and displaying top activity/time; score explicitly not semantic confidence. Preserved working import/music/dialogue/render workflows. Unimplemented AI Director/Color/Styles navigation disabled.
- Source library reveals after media import; initial home layout prioritizes the reference composition. Actual timeline lanes remain connected to stored data. Empty preview is clearly empty; no fabricated gameplay/waveforms.
- Validation: three offscreen desktop checks passed; compileall passed; built wheel and verified packaged cathedral asset; final screenshot inspected. Windows/device playback remain unvalidated. Advanced effect and semantic AI controls from reference still planned.

## 2026-10-01 — Optional Ollama automatic director
- User requested minimal involvement and local AI-driven editing. Verified current Ollama API documentation.
- Added loopback structured-JSON director, independent plan validation, prioritized candidates, global pacing and supported transitions. Connected CLI (--ollama-model/--brief) and desktop mode/model/brief controls. Automatic FFmpeg pipeline executes and validates plans; no model-generated commands or asset paths.
- Records provider/model/plan in analysis sidecar. Missing/invalid Ollama fails explicitly rather than falsely claiming AI operation. Existing heuristic mode and timeline replay retained.
- Tests: eight core tests passed in 8.153s, including transport mock, invalid-plan rejection and actual MP4 from mocked AI plan. Three desktop checks passed. Ollama binary/service absent, so live inference and model quality remain unvalidated.
- Added scrolling inspector to preserve readable controls after adding AI settings. Advanced vision, TTS, reference selection, speed ramps and autonomous quality iteration remain planned.

## 2026-10-01 — Drop/song/create simple mode
- User requested minimal interaction: drop clips, type desired song, automatically create Christian-inspired montages.
- Added native file drag/drop and duplicate handling, local song filename matching with ambiguity selection, one-time saved music folder/model/brief preferences, hidden advanced controls and one-click quick creation with unique automatic output path in OS Movies/Videos/DRIFT.
- Added original Christian closing title for quick mode and persisted faith_message in backward-compatible timelines. FFmpeg drawtext uses a literal text file with expansion disabled. No downloaded songs, fabricated scripture or synthesized speech.
- Validation: ten core tests passed in 8.677 seconds; four desktop checks passed in .325 seconds. Covers local music matching, duplicate drop ingestion, settings persistence, default hidden inspector and real titled render/replay. Screenshot inspected. Previous Ollama integration GitHub CI passed.
- Limitations: song lookup matches local filenames only; library scan bounded to 10,000 entries. Windows drag/drop/device execution and live Ollama quality remain unvalidated. Artistic equivalence to Kaiser, advanced effects and autonomous quality iteration remain goals.
