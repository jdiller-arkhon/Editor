# Architecture

Python package with CLI orchestration. Configuration is immutable and validated. FFmpeg provides media decoding/encoding. NumPy will provide bounded-resolution signal analysis. The initial system runs locally without API keys or model downloads.

Planned flow: probe imports → activity/music analysis → candidate selection → typed timeline → render → decode validation. Game adapters will contribute scored events to a common candidate schema; generic activity must remain usable without them. A future desktop GUI will call the same engine rather than own rendering logic.
