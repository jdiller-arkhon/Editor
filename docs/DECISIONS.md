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

## 2026-10-01 — Frame timing and media staging

Quantize automatically directed cuts to complete output frames and supply explicit concat
shot durations. Encode MP4 intermediates in native temporary storage because muxers seek
back to write headers; workspace-backed random writes produced truncated/missing moov data
in the real-footage test. After validation, sequentially copy into a destination staging file,
flush/fsync and hard-link the final path without replacing existing files. Remove the stage
on success/failure. This also handles different source/destination filesystems without publishing
an incomplete export. Temporary storage needs sufficient space for encoded shots and final video.

## 2026-10-01 — Generator quality instead of sample post-processing

The user's priority is automatic generation quality. Implement shared engine improvements:
lossless intermediates and one delivery encode; bounded pair compositing with fixed musical
cut centers; candidate-first selection before fallback filling; source-detail/upscaling reporting;
energetic local-song excerpt selection with persistent offsets. Use held edge handles explicitly
rather than silently repeating extra footage. Reject known HDR sources until tone mapping exists.
Do not equate CRF/1080p with native detail, semantic editing judgment or studio-quality validation.

## 2026-10-02 — Subtle story direction and Claude continuity

Keep the workspace visually neutral and default faith influence to hope/perseverance with an editable original closing line. Offer explicit Christian and neutral choices in Creative controls. Preserve custom lines across tone changes and persisted settings; tone changes replace only recognized preset text. Both automatic and manual generation pass the selected line into the real renderer. Keep the repository, branch, tests and development log as the handoff source of truth; root CLAUDE.md and docs/CLAUDE_HANDOFF.md describe tested implementation and concrete regression safeguards.
