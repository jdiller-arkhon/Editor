# Testing

Run `python -m unittest discover -s tests -v`.

Foundation tests verify settings validation and environment discovery. Timeline tests verify serialization, invalid bounds and non-overlapping direction. Mandatory integration generates 12 seconds of moving synthetic video with audio and 8 seconds of pulsed music, analyzes both, renders a six-second MP4, checks onset candidates, reloads/re-renders the timeline and fully decodes both exports. It also verifies refusal to overwrite and rejects invalid/duplicate imports.

Synthetic tests verify mechanics, not real gameplay event detection or editorial quality. No actual gameplay/music was supplied for this session. Windows and GPU execution remain unvalidated. CI installs FFmpeg and tests the CPU pipeline; it does not silently skip media validation.
