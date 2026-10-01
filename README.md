# Universal AI Gaming Montage Editor

Personal-use, local gaming montage editor. Development status: foundation checkpoint.

## Status
- IMPLEMENTED: validated configuration and local CPU/GPU/FFmpeg discovery.
- PLANNED: media import, heuristic analysis, timelines, rendering, GUI, game adapters and AI direction.

## Requirements and development
Python 3.11+, NumPy and FFmpeg/FFprobe on PATH. Windows 10/11 or Linux. CPU encoding is the baseline; no GPU or AI models required. Encoder detection reports availability, not a validated GPU encoding session.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
python -m pip install -e .
montage-editor doctor
python -m unittest discover -s tests -v
```

Source lives in `src/montage_editor`, tests in `tests`, engineering records in `docs`. Large user assets belong outside Git (ignored local directories: `assets`, `models`, `proxies`, `cache`, `exports`). Never commit footage, songs, model caches or credentials.

All games are intended to use a generic analysis baseline; no game-specific adapter exists yet. No export or AI editing capability is implemented in this checkpoint.
