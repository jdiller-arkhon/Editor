# Architecture

Python CLI calls a reusable local engine. Immutable Settings define dimensions, frame rates and clip bounds. FFprobe inspects imported media; FFmpeg decodes sampled grayscale frames and mono audio; NumPy calculates motion and loudness signals. Analysis is chunked to avoid loading raw recordings into RAM.

Music analysis finds positive RMS changes, with 250ms peak separation. This detects transients, not a reliable tempo/beat grid. Candidate activity combines normalized motion (75%) and loudness (25%), or motion alone for silent gameplay. Motion can favor camera shake or menus; loudness can favor irrelevant noise.

The deterministic director ranks candidate peaks, places clips around them, seeks unused nearby intervals and chooses cuts from onsets within configured duration bounds. It never repeats source intervals merely to fill time. A shortage yields a shorter export; the validation sidecar flags this.

Versioned JSON timelines contain absolute source paths, source offsets/durations, scores, music and settings. The renderer checks source bounds, creates consistently encoded temporary clips, concatenates video, adds music/fades and validates metadata plus full decode. It publishes the final file only after validation; temporary files are cleaned. Project sidecars are written after publication, so a disk failure during sidecar writing can leave a valid export without a complete project. No resumable jobs exist yet.

Future desktop UI should call the engine. Game adapters should return candidate timestamp/score evidence in a common schema. Semantic evidence and models will require separate evaluation; generic motion must remain usable without them.

The `editing.py` module defines output-to-source timing and matched video/audio retiming filters.
Timeline clip profiles and anchor metadata remain backward compatible through defaults.
The renderer retains gameplay audio through concat, mixes music/voice/gameplay, then optionally
performs measured two-pass mastering. See EDITING.md for exact quality limits.
