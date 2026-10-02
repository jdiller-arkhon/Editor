# Local automatic direction with Ollama

## User workflow

Import gameplay, choose music, select Automatic • Ollama, enter the name of an installed local model, optionally enter a short creative brief, then Generate. The engine measures activity, asks Ollama for a bounded plan, fits the timeline to music onsets, mixes any user-supplied dialogue, renders and validates the export. Manual clip selection is not required.

Install Ollama separately from https://ollama.com/download and run a downloaded local model compatible with structured JSON outputs. Use `ollama list` to find model names and `ollama serve` if the local service is not running. Model selection depends on available VRAM/RAM; the app does not download models or provision Ollama. A desktop GPU can help inference, but neither GPU execution nor local model quality has been validated here.

```sh
montage-editor create --gameplay gameplay.mp4 --music song.wav --output exports/ai.mp4 --ollama-model YOUR_INSTALLED_MODEL --brief "Cinematic Christian hope, restraint followed by a confident finish"
```

Without `--ollama-model`, the existing automatic activity engine runs without a model. Desktop defaults to that baseline; choosing Ollama requires a model name. Loaded timeline replay renders stored decisions without another inference request.

## Implemented, experimental scope

Ollama receives up to 120 activity-ranked candidate records with anonymous source IDs, timestamps, source durations and motion/audio scores. No footage, audio, frames or local filenames are sent to the model. It prioritizes candidates, sets global clip-length bounds and chooses implemented cut, fade, zoom, push, blur, dissolve or cinematic compositing plus duration. The director preserves actual scores, appends unranked candidates and fits non-overlapping source clips to musical onsets. Original requested duration remains the target; limited footage may shorten output. Dialogue remains user-provided and timed; AI settings override manual transition/pacing for new generation.

This is metadata-driven direction, not visual understanding. Models cannot recognize kills, inspect Christianity-related visuals, add absent effects, synthesize dialogue or verify theology. There is no TTS, automatic reference import, semantic effect planning, self-improvement loop or studio-quality guarantee.

## Validation boundary and failure behavior

Uses the loopback `/api/chat` endpoint at 127.0.0.1:11434, `stream:false`, JSON Schema format, bounded token budget and a 120-second request timeout. Ignores system proxies and rejects redirects. Choose a downloaded local model; a cloud-backed model configured in Ollama may itself use external inference. No API keys required by this integration.

The app independently validates candidate IDs, duplicates, field allowlist, finite numeric bounds, min/max clip lengths, supported transitions and rationale length. Model output is data only; never executed as commands or accepted as asset paths. It cannot replace source footage or modify export paths. Invalid/unavailable inference produces a clear error and no export; no silent fallback masquerades as AI success. User can explicitly select baseline mode instead.

The `.analysis.json` sidecar records provider, model, validated plan and evidence limitations. Replay persists actual timeline decisions. Rationale is explanatory metadata, not narration or verified fact.

## Tests and evidence

Core tests, including mocked structured transport, invalid/duplicate/unknown plan rejection, connection-error behavior and actual MP4 rendering from a mocked director plan. Desktop checks cover controls, reference artwork and worker behavior. Live Ollama/model inference is not tested in this environment because Ollama is absent. Do not label mocked tests as proof of model quality.

## Official API references

- https://docs.ollama.com/api/chat
- https://docs.ollama.com/capabilities/structured-outputs
- https://docs.ollama.com/api/tags

## Next automation stages — planned

Vision-based event evidence, confidence labeling, voice transcription and timing, licensed dialogue libraries, optional original narration/TTS, advanced effects with measurable controls, automatic output comparison and Windows/GPU performance validation. These require capabilities beyond a text model.

## Low-interaction desktop mode

The home screen now exposes drop clips, song title and Create Christian montage. Music folder and local model are configured once and remembered using OS QSettings. Advanced controls can be reopened. Quick-create exports automatically to a unique OS Movies/Videos/DRIFT filename and adds an original closing title. Music-title lookup is local filename matching only. No streaming/downloading provider or TTS is implemented. Missing model inference still fails explicitly rather than silently presenting a baseline result as AI.

Quick-create now uses the shared lossless processing/high-quality delivery engine and an
energetic excerpt of the selected local song. Excerpt selection measures energy/variation,
not lyrics or phrases. The recorded music_start offset is used consistently in analysis,
rendering and replay. Advanced can disable automatic excerpt selection. Local-model ranking
continues to take precedence; its transition choice still must pass the implemented allowlist.


## Claude vision editor (opt-in, implemented; live quality unvalidated)

`vision_director.py` adds an AI editor that actually looks at the footage. The local engine still
finds activity candidates and owns every timing decision (beat grid, ramps, rendering). Up to 24
candidates, interleaved across sources, are sent to Claude (`claude-opus-5-5`, adaptive thinking,
effort `high`, server-side `fallbacks: "default"`) as three 512-px JPEG frames each (0.6 s before,
at, and after the activity peak) plus anonymous source IDs and timestamps. File names and paths are
never sent. Claude returns schema-constrained JSON: highlight 0-10, event type (elimination, clutch,
objective, movement, menu_or_loading, ...), usable flag, which frame is the peak, a short note and a
preferred story order. Every field is validated; invented IDs, out-of-range scores, unknown events or
duplicates reject the whole review before rendering.

Effect on the edit: reviewed moments are re-scored by Claude's highlight and re-anchored to its peak
frame; unreviewed candidates keep 30% of their activity score; unusable footage (menus, loading,
scoreboards) is reserved so neither anchored shots nor fallback fills can cover ±1 s around it. The
cinematic director's energy matching then puts the strongest judged moments on the loudest music,
with Claude's story order as a tie-break. Reports record events, usable count and token usage.

Enable with `montage-editor create ... --claude-editor` or Director → "Automatic • Claude vision editor"
(the UI states that frames are sent to Anthropic). Requires `pip install -e '.[ai]'` and
`ANTHROPIC_API_KEY` or `ant auth login`. Roughly 72 images ≈ 15-20k input tokens per montage.
Tests use a mocked transport with real frame extraction and real renders; no live Claude review has
been run in this repository, so judgement quality on real gameplay is not yet measured.


### 2026-10-02 upgrade: frame strips and cut review

- Each reviewed candidate is now one image: six numbered frames 0.5 s apart (3 s, 768×288), so Claude
  sees the action unfold and picks `peak_frame` 1–6; the moment is re-anchored to that frame's time.
  Roughly 300 image tokens per candidate (about half of the previous three separate frames).
- **Cut review (second pass):** after the director plans the cut, Claude sees a contact sheet of the
  planned shots S1..Sn (each at its key moment, with song position, intensity, phrase/lift starts and
  which shot carries the closing line) and up to eight unused alternates A0..A7 with their scores.
  It may propose up to four swaps. Each swap keeps the shot's musical timing, speed profile and
  accents; `pipeline.swap_shots` rejects swaps whose moment would fall outside the shot, reuse
  footage, cover a non-gameplay span or exceed the source. Applied and rejected swaps, reasons and
  notes are recorded in the analysis sidecar. A failed review keeps the first-pass cut and records why.
- Excluded (non-gameplay) candidates are never sent for review. Live judgement quality remains
  unmeasured here (no credentials); tests use a mocked transport with real images and renders.
