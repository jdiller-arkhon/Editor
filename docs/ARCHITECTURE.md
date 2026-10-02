# Architecture

Python CLI calls a reusable local engine. Immutable Settings define dimensions, frame rates and clip bounds. FFprobe inspects imported media; FFmpeg decodes sampled grayscale frames and mono audio; NumPy calculates motion and loudness signals. Analysis is chunked to avoid loading raw recordings into RAM.

Music analysis computes positive log spectral flux (10 ms hops, all bins plus a <200 Hz band), latency-compensated to the analysis window centre, and picks attacks with 250ms peak separation. `rhythm.py` then estimates tempo by envelope autocorrelation with a broad log-tempo prior, tracks beats by dynamic programming, picks the 4/4 downbeat phase with the strongest low-band accents, and marks phrase boundaries on an assumed four-bar grid plus measured bar-energy rises/falls. A confidence (periodicity × beat-on-attack share × interval steadiness) gates use; below 0.5 the attack path is kept. This is not lyric, chorus or genre recognition, and odd meters are not modelled. Candidate activity combines normalized motion (75%) and loudness (25%), or motion alone for silent gameplay. Motion can favor camera shake or menus; loudness can favor irrelevant noise.

The deterministic director ranks candidate peaks, places clips around them, seeks unused nearby intervals and chooses cuts within configured duration bounds: with a confident beat grid, a dynamic-programming path over beats (rewarding downbeats, phrase boundaries and power-of-two beat lengths, penalising shots that run across a phrase boundary, targeting shorter shots in louder passages); otherwise the first attack after the minimum length. Cinematic impact ramps land on measured lifts or loud phrase starts in beat mode, and candidate activity is matched to music intensity. It never repeats source intervals merely to fill time. A shortage yields a shorter export; the validation sidecar flags this.

Versioned JSON timelines contain absolute source paths, source offsets/durations, scores, music and settings. The renderer checks source bounds, creates consistently encoded temporary clips, concatenates video, adds music/fades and validates metadata plus full decode. It publishes the final file only after validation; temporary files are cleaned. Project sidecars are written after publication, so a disk failure during sidecar writing can leave a valid export without a complete project. No resumable jobs exist yet.

Future desktop UI should call the engine. Game adapters should return candidate timestamp/score evidence in a common schema. Semantic evidence and models will require separate evaluation; generic motion must remain usable without them.

The `editing.py` module defines output-to-source timing and matched video/audio retiming filters.
Timeline clip profiles and anchor metadata remain backward compatible through defaults.
The renderer retains gameplay audio through concat, mixes music/voice/gameplay, then optionally
performs measured two-pass mastering. See EDITING.md for exact quality limits.

`transitions.py` composes bounded two-shot pieces around unchanged cut centers. `music_sections.py`
selects a measured energetic song excerpt. Timeline music_start and quality persist through replay.
Video/audio intermediates are FFV1/PCM; the final delivery encode is the sole lossy encode after
processing. See RENDERING.md for memory/disk requirements and source-detail/color limitations.
