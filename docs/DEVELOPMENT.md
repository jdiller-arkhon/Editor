# Development

At each session fetch GitHub, inspect branches/status, read README and the development log, then run tests. Commit and publish meaningful verified checkpoints. Do not use chat as the source of project status.

Install with `python -m pip install -e .`; run `python -m unittest discover -s tests -v` and `python -m compileall -q src`. Normal CI requires FFmpeg and performs a real render/replay/full decode; missing executables fail the tests. No GPU tests currently exist.

The root foundation was initialized on main. Substantial editing-engine work uses `feat/working-montage-pipeline`. Preserve completed work in GitHub before concluding a session. User footage and exports must stay outside Git.
