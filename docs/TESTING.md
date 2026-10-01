# Testing

Run `python -m unittest discover -s tests -v`.

Foundation tests verify settings validation and environment discovery. Timeline tests verify serialization, invalid bounds and non-overlapping direction. Mandatory integration generates 12 seconds of moving synthetic video with audio and 8 seconds of pulsed music, analyzes both, renders a six-second MP4, checks onset candidates, reloads/re-renders the timeline and fully decodes both exports. It also verifies refusal to overwrite and rejects invalid/duplicate imports.

Synthetic tests verify mechanics, not real gameplay event detection or editorial quality. No actual gameplay/music was supplied for this session. Windows and GPU execution remain unvalidated. CI installs FFmpeg and tests the CPU pipeline; it does not silently skip media validation.

Cinematic coverage additionally checks retimed source consumption and anchor mapping,
visible motion/frame changes, audio RMS/peak bounds and soundtrack spectral presence,
measured two-pass mastering, silent-music rejection and mixed silent/audio source concat.
Run desktop checks separately with `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests -p desktop_checks.py -v`.

A sixteen-shot fractional-duration render guards against cumulative concat timing errors. Director cuts are quantized to output frames; concat receives explicit shot durations. The real-gameplay test recipe and credits are in TEST_MONTAGE.md.
