# DRIFT / Universal AI Gaming Montage Editor

Continue this existing project. Do not initialize a different repository or replace the engine with a UI mockup.

1. Inspect `git status`, fetch GitHub, determine the actual current branch/default branch and review recent commits.
2. Read `docs/CLAUDE_HANDOFF.md`, `README.md`, `docs/DEVELOPMENT_LOG.md`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md` and `docs/RENDERING.md` before changing architecture.
3. Install the project and establish a test baseline: `python -m unittest discover -s tests -v`; desktop checks run separately with `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests -p desktop_checks.py -v` on Linux.
4. Use the real generator and renderer. Mandatory tests must render/decode actual media; never silently skip FFmpeg failures or label mocked Ollama responses as live inference validation.
5. Preserve duration/frame-clock checks, lossless native-temp processing, atomic no-overwrite publication, validated model plans, source-interval non-reuse and backward-compatible timeline defaults.
6. Improve automatic editorial quality, not just a demonstration video. No fabricated waveforms, recognized kills, source footage, GPU benchmarks or studio/Kaiser-equivalence claims.
7. Maintain subtle, monochrome UI styling and explicit optional Christian storytelling. Never overwrite a custom closing line when changing tone. Existing timeline replay retains its stored message/settings.
8. Large footage/music/models/renders/caches/secrets stay outside Git. Update docs/log, run relevant tests, make meaningful commits, push and verify reviewable checkpoints in `jdiller-arkhon/Editor`.

At handoff (2026-10-02), development is on `feat/working-montage-pipeline`, PR #1; default `main` contains only the initial foundation. Verify this state from GitHub because it may change. Do not start from main and accidentally discard completed work.
