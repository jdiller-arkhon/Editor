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

## 2026-10-01 — Actual sample render and duration regression
- Produced a 12-second 720p sample through the actual CLI using animated generated cathedral artwork and synthesized music, white fades and a Christian closing title. This demonstrates mechanics, not gameplay/Kaiser-level artistry or live AI inference.
- Sample inspection exposed video ending at 6 seconds while audio/container lasted 12. Output seeking after input interacted with frame processing. Moved accurate seek before input and now independently require video/audio stream durations to match timeline; container-only validation was insufficient.
- Regenerated sample has full 12-second video/audio coverage, full decode and verified late title frame. Ten core tests passed in 8.976 seconds with stricter validation. Large sample/media are excluded from Git.

## 2026-10-01 — Cinematic editing and audio checkpoint
- Objective: address the rejected flash/noise sample with connected editing features, not additional synthetic demonstration promises.
- Added editing.py output/source mapping and piecewise 1.4×/0.6×/1.4× retiming with pitch-preserving audio. Timeline persists validated activity anchors and mix/effect settings.
- Music now uses bounded spectral-flux attack detection at 10 ms hops and rejects silent tracks. Director aligns activity peaks inside shots when possible, varies source selection and builds/resolves heuristic activity. It still does not recognize kills or downbeats.
- Renderer retains gameplay audio, handles silent sources, adds restrained zoom edges, real narration sidechain ducking, measured two-pass loudnorm and limiting. Desktop quick mode connects cinematic settings; Ollama may select zoom with validated schema.
- Documentation: README, ARCHITECTURE, DECISIONS, EDITING, TESTING and ROADMAP updated to distinguish implemented tools from artistic/semantic goals.
- Tests: 11 core tests passed in 16.923 seconds, including real render/replay, audible music spectrum/RMS/peak checks, changed video frames, mastering and mixed silent/audio sources. Four desktop checks passed offscreen. Compileall passed; whitespace check corrected. Earlier mastering test exposed suppressed FFmpeg measurement logs; measurement now explicitly enables info logging.
- No GPU, live Ollama, Windows/device playback or real-gameplay creative benchmarks claimed. Ramps are piecewise, zoom is not optical-flow compositing, narration/reference selection remains manual and Christian story meaning is not autonomously verified.
- Next priority: real user gameplay/music/narration evaluation; semantic event evidence and phrase-aware timing, then smooth retiming/color/story controls.

## 2026-10-01 — Real-gameplay sample and concat regression
- User requested a test montage with the new tools. No uploaded gameplay/music was available. Downloaded credited Xonotic gameplay by Drummyfish/Xonotic developers (GPL-3.0-or-later) and the US Marine Band/Sara Sheffield Amazing Grace recording (public domain in the US per source).
- Prepared source video seconds 20–130 and music seconds 30–58. Automatic cinematic director selected twelve shots for 24 seconds at 720p/30fps, four impact-profile shots, zoom edges, .10 gameplay/.9 music mix, measured mastering and original Christian closing text. No live Ollama or added narration.
- Initial export attempts failed independent stream-coverage validation; no failed export was published. Added complete-frame cut durations, explicit concat shot durations and more informative validation errors. Retained diagnostics subsequently rendered 720 full video frames and 24-second video/audio streams. Added sixteen fractional-duration-shot regression to mandatory integration coverage. Workspace intermediates also exhibited missing MP4 moov headers despite encoder exit success; native /tmp intermediates passed. Moved seek-dependent FFmpeg output to native temporary storage, then sequentially copy to a destination staging file and hard-link atomically without overwriting. Coverage checks remain mandatory.
- Validation: eleven expanded core tests passed in 24.574 seconds after native-staging fix. Example CLI help under installed environment, compileall and whitespace checks passed. Output contact sheet inspected, closing title visible. Measured output integrated loudness −16.01 LUFS, true peak −3.11 dBTP. Full decode passed. Prior cinematic checkpoint's GitHub core and desktop CI both passed.
- Added examples/render_gameplay_test.py and docs/TEST_MONTAGE.md for repeatable recipe, source/license credits and honest artistic scope. Media/render/reproduction archive remain outside normal Git history.
- Limitations: single-map test footage, no semantic kill selection or live AI model. Hypothetical studio/Kaiser-level quality is not asserted. Next: user footage evaluation, semantic selection and phrase-aware story editing.

## 2026-10-01 — Automatic montage generator quality
- User requested stronger transitions/music/rendering, then clarified that app-generated quality, not an improved demonstration video, is the objective. Stopped the in-progress evaluation sample and focused on engine/UI integration; no new sample is delivered in this checkpoint.
- Added transitions.py: actual smooth push, zoom, horizontal blur and dissolve compositing; cinematic mode varies directions/styles. Pair jobs replace cut neighbourhoods with held-edge handles, preserving musical cut centers and duration without a graph that decodes all shots at once. Reports record actual boundaries/effects/handle type.
- Replaced lossy intermediate H.264/AAC with lossless FFV1/24-bit PCM and a single final delivery encode. Added Draft/High/Master presets (CRF 23/16/12), slow high-quality encode, 320 kbps AAC, Lanczos scaling, BT.709 SDR conversion/tags, source-size/upscale metadata and explicit known-HDR rejection. This is not lossless final delivery, calibrated grading or recovered source detail.
- Director now tries all genuine candidate anchors before unused-interval fallback, preventing repeated adjacent filler around the first ranked candidate. Added music_sections.py to choose an energetic varying excerpt of the user's selected song; exact offset persists and is used in both attack analysis and rendering/replay. No online song acquisition or phrase/lyric understanding.
- Desktop quick-create defaults to 1080p/High/cinematic blends/mastered audio/automatic music section; Advanced exposes quality, individual transitions and excerpt toggle. CLI exposes --quality. Ollama schema validates implemented compositing choices.
- Tests: fourteen mandatory core tests passed in 30.605 seconds; five offscreen desktop checks passed in .302 seconds. Includes real red/blue two-image boundary blending, all five transition modes, cut-clock/duration preservation, an actual two-frequency soundtrack excerpt render, quality validation and quick-create generator wiring. Prior core/duration/audio tests retained. Compileall and whitespace checks passed.
- Limitations: held-frame transition handles can freeze motion briefly; no optical flow, subject tracking, semantic kills, calibrated color/HDR conversion, musical phrase/lyric recognition or automatic religious narration. Windows/device playback/GPU and live Ollama remain unvalidated. Temporary lossless media require substantially more storage and CPU time.
- Next priority: real user gameplay/music editorial benchmark and semantic moment/phrase evidence, followed by smooth retiming and narrative/caption generation. Artistic quality cannot be certified by encoding settings alone.

## 2026-10-02 — Refined workspace and Claude handoff
- Objective: improve the actual UI, make Christian influence subtler and prepare continuation in Claude in the existing repository. Starting branch was clean at 96ef2d6; main still held the foundation and PR #1 contained the working application. Previous GitHub core/desktop CI succeeded.
- Refined desktop.py and workspace_widgets.py: layered graphite panels, quieter architectural texture, neutral copy, clear preview/intake hierarchy, disabled playback until media exists, scrollable compact-window layout and simplified navigation. Replaced prominent cross imagery with film/viewfinder geometry. Updated docs/ui-preview.png from the actual offscreen desktop and visually inspected home/creative-control layouts.
- Added persisted Subtle/Christian/Neutral tone selection and editable closing line. Default is Keep the faith.; explicit Christian remains optional. Custom captions survive changes/restart, including an empty optional title. Connected settings to automatic/manual generation without changing render-engine behavior.
- Added CLAUDE.md and docs/CLAUDE_HANDOFF.md with repository/branch continuity, module map, setup, real test commands, known regressions, truthful implementation status and a kickoff prompt. Updated README, storytelling, assets, roadmap and decisions. No automatic transfer of a Claude account/session is performed.
- Tests: fourteen mandatory core tests passed in 44.504 seconds with actual FFmpeg renders; six offscreen desktop checks passed in .840 seconds, including quick-create wiring and tone/custom-line persistence. Compileall and git diff --check passed. No additional artistic benchmark this session.
- Limitations: Windows, GPU, physical device playback and live Ollama remain unvalidated. Semantic gameplay/phrase understanding, smooth ramps, automatic narration and cancellable jobs remain unfinished. The UI refinement does not establish studio-quality montage judgment.
- Next priority: use real gameplay/music editorial evaluation to add semantic moment and musical phrase evidence, preserving stream-duration, frame-clock, audio/mastering and native-staging regressions described in the handoff.

## 2026-10-02 — Beat-grid cut planning (Claude continuation)
- Starting state verified: PR #1 head 37dfe35 on feat/working-montage-pipeline; work continues on claude/drift-montage-handoff-poejrd based on that head. Baseline before changes: 14 core tests OK (34.3 s), 6 desktop checks OK after installing Qt system libraries.
- Problem: cuts were placed on the first spectral-flux attack after `minimum_clip`; broadband hats/fills dominated, there was no beat, bar or phrase notion, and the auto excerpt started on a 1 s grid regardless of bars.
- Added rhythm.py: autocorrelation tempo, DP beat tracking, low-band downbeat phase, four-bar grid plus measured energy rise/fall phrase marks, confidence gate, global DP cut planner and `alignment_report`. music_analysis computes low-band flux, latency-compensates onsets and stores the grid. direct() separates segment planning (beat or attack) from the unchanged footage selection/non-reuse loop. Auto excerpt snaps to phrase marks/downbeats when confident. Validation report includes `music_alignment`; desktop status names the measured BPM only when beat pacing was used. Ollama system prompt updated to describe beat-grid fitting.
- Measured on decoded synthetic tracks: tempo within 0.02 BPM at 90/128/150, beat error ≤8 ms (mean ≈0), downbeat phase correct, white noise confidence 0.07 → attack fallback. On a 30 s 128 BPM fixture: 13 cuts, 100% on beats and downbeats, 4/4 phrase boundaries cut, 4-beat shots after the lift vs ~8-beat shots before it (greedy prototype had cut 1 beat early on 2 of 4 phrases).
- Tests: 19 core tests OK (41.9 s) including five new rhythm tests with real FFmpeg decode/render; 7 desktop checks OK, including the new beat-grid status check. Mutation checks confirmed the new tests fail when attack pacing is forced or downbeat phase is shifted.
- Limitations: no real licensed-music validation; swing, rubato, tempo changes, half-time drops and non-4/4 meter are not modelled; phrase grid is assumed four-bar; no beat/phrase correction UI; gameplay events are still activity heuristics, not semantic.
- Next: per-boundary transition choice (hard cuts on regular beats, composited blends reserved for phrase boundaries/lifts) without changing old-timeline replay; then real-footage/real-music benchmark.

## 2026-10-02 — Ramps, punch-ins and per-cut transitions (Claude continuation)
- User asked for Kaiser-level quality. That equivalence cannot be verified here (no frame-level reference study, no user footage); implemented the editorial techniques the generator lacked instead.
- Added smooth `ramp` speed profile (editing.py), `Clip.accents` beat punch-ins and `Timeline.boundary_transitions` per-cut hard cut/blend choice (transitions.py compose `per_cut`). Excerpts inherit the whole-song grid/energy scale; the first version re-analysed the excerpt alone, lost its first downbeat and mis-numbered bars, and the end-to-end test passed vacuously with no effect applied until fixed.
- Measured: rendered ramp frames follow the planned source clock within 60 ms (luma-encoded clock), unramped would be 0.25+ s off; punch frames differ strongly on the accent and return to the plain render after it; a 'cut' boundary has no blended frame while the next 'smoothleft' frame shows both shots.
- Tests: 24 core tests OK (51.5 s), 7 desktop checks OK.

## 2026-10-02 — Claude vision editor (Claude continuation)
- Added vision_director.py (ClaudeDirector), `ai_editor` in create_montage, `--claude-editor` CLI, desktop Director option with disclosure, `[ai]` extra (anthropic>=1.11). Exclusion of unusable footage is enforced in direct() by pre-reserving spans.
- Found and fixed while testing: matching reviews by object identity broke on rebuilt lists (now source/time); missing credentials surfaced as a raw SDK TypeError/CredentialsError (now a clear message); SDK import made optional when a client is injected so CI without the extra still runs the tests.
- Tests: 5 vision tests (real frame extraction, request shape incl. no paths, strict validation, refusal/max_tokens, credentials, real render honouring exclusions). No ANTHROPIC credentials in this container: no live API call made.

## 2026-10-02 — White, colour-accented UI redesign (Claude continuation)
- User asked for a primarily white UI, then a new font, new structure and more colour. Delivered white monochrome first (6897774), then this redesign: bundled OFL Manrope/Sora, top app bar, Create card with visible clip list and gradient action, side-by-side preview, colour-coded timeline lanes, colour chips and status. Iterated from offscreen screenshots: fixed a caption overlapping the empty state, a missing combo arrow, stretched chips, lane outlines, step headers painting over the card tint and a page clamped below its content height.
- Desktop checks: 9 OK (new: bundled fonts register, theme is white with accent, chevron path resolves, window edge renders white).

## 2026-10-02 — Music from links (Claude continuation)
- Added music_sources.py, desktop “Add from link” (background job, rights notice), CLI `add-music`, `[links]` extra (yt-dlp), doctor reports yt-dlp and JS runtime. CI core job now installs `[ai,links]` so these tests run.
- Live check from this container: Spotify track pages readable (title/artist/duration); YouTube search resolves but downloads are blocked by YouTube's bot check on datacenter IPs, so no live YouTube download was validated. Recent yt-dlp also wants a JS runtime (Deno) for full YouTube support.
- Tests (real yt-dlp against a local HTTP server): audio-only .opus output, provenance sidecar, beat analysis of the result, no overwrite/re-download on repeat (bug found and fixed: the extract step overwrote, then a stray .webm was returned), Spotify→YouTube match accepted at matching duration and deleted at mismatch, local library preferred, playlist/foreign-host rejection, friendly bot/missing-extra errors. 35 core tests, 10 desktop checks OK.

## 2026-10-02 — Non-gameplay exclusion, transients, hero placement (Claude continuation)
- User asked for all recommended improvements and clarified: improve the app, do not remake demo montages. Real footage is used only to measure detectors.
- Hand-labelled 270 frames (2 s spacing) from two stretches of a CC BY-SA Xonotic duel. Rejected a first static-text detector (caught 1/3 training deaths). HUD-presence detector: training 3/3 death spans, 0 false; held-out all death/scoreboard spans incl. two my labels missed, 3 respawn false spans at threshold 0.5, 0 at 0.35 (post-hoc). Shipped implementation (keyframe mask, 4 fps) reproduced this on both clips; 9 min analysed in 45 s CPU.
- Found while testing: candidates on the fading edge of an excluded span kept a non-zero score (now dropped); the director could leave the single best moment unused when many similar clips matched the music better, or when it sat at a source edge (fixed: hero placement; contained edge placement). Hero test mutation-checked.
- Tests: 40 core OK, 10 desktop OK. Kill-feed/hit-marker reading is not implemented: it needs per-game screen regions/OCR and was not attempted generically.

## 2026-10-02 — Claude strips and cut review (Claude continuation)
- Moment review now sends one numbered 6-frame strip per candidate; new review-the-cut pass with validated swaps (closing shot included). Tests: request shape (4 strips, 768×288), peak_frame validation, swap validation limits, swap rules (reuse, non-gameplay), applied swaps land inside their shots with total duration preserved, failed review keeps the cut. 42 core tests OK.

## 2026-10-02 — Music structure (Claude continuation)
- Added bass/timbre measurement, shared `structure()` for bars/phrases, drop/build marks, timbre-novelty downbeats, manual grid override (story/CLI/desktop with tap tempo), drop-aware excerpt choice, drop hero placement and build punch-ins. Found and fixed: cut_mode equality checks would have dropped manual grids from cinematic transitions; tap-tempo reset on non-increasing clock.
- Tests: 5 new structure tests on decoded synthetic songs (drop vs hat lift, chords-only downbeats, override, excerpt, drop hero/build); drop and timbre terms mutation-checked (first chord test did not isolate timbre and was replaced). 47 core, 11 desktop OK. No ground-truth labels for real music yet.

## 2026-10-02 — Finishing (Claude continuation)
- Added craft.py and Timeline finishing fields; desktop controls; bundled 4 CC0 swishes (~24 KB). Tests on rendered output: interpolation held-frame reduction, look saturation/monochrome, blur softening, follow-crop keeps an off-centre subject visible with no letterbox (mutation-checked: a centred crop fails), swish present on a push and absent on a hard cut. First test footage was flawed (saturated testsrc2, drawbox that cannot animate) and was corrected. 51 core, 11 desktop OK.
