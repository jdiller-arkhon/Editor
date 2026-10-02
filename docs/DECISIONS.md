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

## 2026-10-02 — Measured beat grid drives cut placement

Cutting on the first spectral-flux attack after the minimum length let hi-hats and fills set the
edit rhythm (on a kick/snare/hat fixture the attack picker mostly selected off-beat hats). Cuts now
follow a measured beat grid when its confidence is at least 0.5, chosen by a global dynamic-programming
path rather than greedily, so phrase boundaries reachable only by planning ahead are still cut.
Downbeats assume 4/4; four-bar phrases are an explicit assumption, energy changes are measured.
The attack planner remains the fallback and the analysis sidecar records which planner was used.
No Timeline schema change: replay of existing projects is unaffected. Onset times gained a fixed
latency compensation (half analysis window plus one hop): onsets are now reported ~42 ms later
than before, closer to the true attack; this was calibrated on synthetic attacks, not real music.

## 2026-10-02 — Hard cuts by default, blends where the music turns

Top montage edits are mostly hard cuts on the beat, with transitions, speed ramps and camera
accents reserved for musical events. In cinematic beat mode the director now chooses per cut and
per shot from measured phrase marks and energy rather than applying one effect to every boundary.
Smooth ramps replace stepped ones for new edits; the stepped profile stays valid for replay. These
choices are rules derived from the measured music, not a study of any specific creator's work.

## 2026-10-02 — Claude judges moments, the local engine keeps the clock

The user asked for a top-end AI editor. Heuristic activity cannot tell a kill from a menu. Claude now
reviews frames and judges what happened; it never supplies timestamps beyond choosing among three
fixed frames, commands, paths or effects, so musical sync, frame-clock and non-reuse guarantees remain
local and testable. Cloud review is opt-in and disclosed because it sends footage frames off-machine;
the local activity engine remains the default. Default model is claude-opus-5-5 with server-side
fallback on refusal.

## 2026-10-02 — Music from YouTube/Spotify links without touching DRM

The user asked to add any song from YouTube or Spotify. YouTube audio is fetched with yt-dlp (optional
extra) into the user's music folder as an audio-only file in its original codec, with a provenance
sidecar. Spotify streams are DRM-protected and are never downloaded or decrypted; the public track
page supplies title/artist/duration, a matching local song is preferred, otherwise the top YouTube
search match is used only if its measured duration is within 7 s of Spotify's (else it is deleted).
The UI and CLI show a rights notice: YouTube downloads may breach YouTube's Terms unless the uploader
permits it, and published montages with copyrighted songs are commonly claimed. Playlists, albums,
live streams and >20-minute items are refused.
