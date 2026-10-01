# Decisions

- 2026-10-01: Python + FFmpeg + NumPy for a portable, inspectable first vertical slice. No external model services or credentials required.
- Use unittest so CPU render tests run without an additional test dependency. FFmpeg absence is a failure, not a skipped integration test.
- H.264/AAC MP4 CPU output is the baseline. Encoder listing alone is insufficient evidence of GPU support.
- Heuristic activity/onsets are experimental. No claims of semantic kills, beat accuracy or top-editor quality without corresponding evaluation.
- Avoid repeated footage to fill requested duration. Shorten and report instead.
- Use GitHub's connected app to publish when command-line Git lacks write credentials. Verify resulting refs and align the local checkout to remote commits.

## 2026-10-01 — Explicit cinematic timing and measured audio

Keep cuts and source consumption deterministic while adding bounded piecewise retiming.
Persist anchor timestamps so activity-to-attack alignment can be inspected and replayed.
Favor restrained zoom over automatic flashes. Retain gameplay audio in all intermediate clips;
use silent tracks for absent source audio so concat has a uniform stream layout. Drive ducking
from actual narration and measure the complete mix before optional loudness mastering.
No sound effects are fabricated to compensate for absent footage/events.
