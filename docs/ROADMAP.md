# Roadmap

The current cinematic checkpoint implements bounded retiming, activity-to-attack alignment,
restrained motion zoom, gameplay mixing and measured audio mastering. See EDITING.md.

Next priorities (planned):
1. Evaluate real gameplay, licensed music and narration; add semantic event evidence and manual corrections.
2. Validate the measured beat grid on real licensed music (swing, tempo changes, half-time, non-4/4); add manual beat/phrase corrections and game-adapter confidence labeling. (Initial grid and beat-aligned director implemented 2026-10-02.)
3. Smooth velocity curves, high-frame-rate-aware slowdown and optional optical flow.
4. Reference-guided color, subject tracking, subject-aware transition compositing and semantic sound design.
5. Verified scripture/reference selection, narration/caption generation and narrative review.
6. Cancellable jobs, progress/resource controls and resumable analysis.
7. Windows execution/installer, GPU validation and live Ollama quality benchmarks.

Kaiser-level artistry and studio-quality delivery are goals requiring qualitative evaluation.

## Status after the 2026-10-02 Claude continuation

Implemented and tested: measured beat grid with drops/builds and manual correction; non-gameplay
exclusion from learned HUD presence; gameplay audio transients; hero placement; per-cut transitions,
smooth ramps, punch-ins, interpolated slow motion, looks, motion blur, follow reframe, swishes;
opt-in Claude moment review with 6-frame strips and a review-the-cut pass; music from YouTube/Spotify
links; progress/cancel, presets, preview→final, shot editing; benchmark with optional Claude judge;
Windows CI (tests and desktop checks).

Still open, in priority order:
1. Live validation: run the Claude editor and judge on the user's real footage and songs, and record
   benchmark baselines (no credentials or user footage were available in the cloud session).
2. HUD/non-gameplay calibration on more games (measured on one game so far); kill-feed/hit-marker
   reading per game (not attempted).
3. Ground-truth beat/downbeat/drop labels for real songs; swing, tempo changes and non-4/4.
4. Impact sound effects (no CC0 source reachable in-session), calibrated colour/HDR, GPU encoding.
5. Windows installer/signing (deferred by the user; a PyInstaller spec existed at d8371be); FFmpeg bundling decision.
