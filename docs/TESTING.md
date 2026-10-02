# Testing

Run `python -m unittest discover -s tests -v`.

Foundation tests verify settings validation and environment discovery. Timeline tests verify serialization, invalid bounds and non-overlapping direction. Mandatory integration generates 12 seconds of moving synthetic video with audio and 8 seconds of pulsed music, analyzes both, renders a six-second MP4, checks onset candidates, reloads/re-renders the timeline and fully decodes both exports. It also verifies refusal to overwrite and rejects invalid/duplicate imports.

`test_rhythm.py` writes synthetic songs with known tempo, beat offset, downbeat accents and an energy lift, decodes them through FFmpeg and checks tempo (±0.5 BPM), beat timing (<20 ms), downbeat phase, a single lift mark and noise rejection. Director tests check frame-quantized beat cuts, phrase hits, energy-driven shot length, impact placement and the infeasible-grid fallback. An end-to-end render checks the automatic excerpt starts on a downbeat and every cut of the exported timeline sits on a beat. These were mutation-checked (forcing attack pacing and shifting downbeat phase both fail).

Synthetic tests verify mechanics, not real gameplay event detection or editorial quality. No actual gameplay/music was supplied for this session. Windows and GPU execution remain unvalidated. CI installs FFmpeg and tests the CPU pipeline; it does not silently skip media validation.

Cinematic coverage additionally checks retimed source consumption and anchor mapping,
visible motion/frame changes, audio RMS/peak bounds and soundtrack spectral presence,
measured two-pass mastering, silent-music rejection and mixed silent/audio source concat.
Run desktop checks separately with `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests -p desktop_checks.py -v`.

A sixteen-shot fractional-duration render guards against cumulative concat timing errors. Director cuts are quantized to output frames; concat receives explicit shot durations. The real-gameplay test recipe and credits are in TEST_MONTAGE.md.

Composite tests render all five blend modes. Red/blue fixtures verify both images contribute
at a boundary and that original cut time/duration remain unchanged. A two-frequency song fixture
verifies that automatic excerpt selection and actual rendered audio use the same offset.
The desktop quick-create test verifies real generator arguments (1080p, high quality, cinematic
transitions, mastering and automatic song-section selection), preventing disconnected controls.


## Benchmark (`montage-editor benchmark OUT.mp4 [OUT2.mp4 ...] [--judge] [--report results.json]`)

Scores rendered montages from their sidecars and the delivered file: sync (cuts on beats/downbeats,
phrase boundaries cut), variety (sources, visual change between neighbouring shots, spread across
each source), integrity (seconds built on non-gameplay spans, full decode), highlights (share of the
strongest analysed moments used, used vs available score, strongest shot on intense music), craft
(ramps, punch-ins, blends vs hard cuts, finishing) and delivery (integrated LUFS, peak). `--judge`
adds a strict Claude rubric grade (moments, variety, pacing, story, overall) from a contact sheet of
the finished edit. Use it to compare settings or versions on the same footage and song; the numbers
expose trade-offs and regressions, they do not certify quality.
