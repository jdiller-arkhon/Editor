# Local AI director (Ollama vision model)

**Current default.** `vision_director.LocalDirector` sends six-frame JPEG strips and contact sheets (never filenames) to a vision model served by Ollama on 127.0.0.1 (`/api/chat`, `format` = JSON schema, no proxy, no redirects, cancellable mid-request). It reviews candidate moments in batches of 4, directs the edit on the fixed beat slots (moment, treatment, transition per slot) and reviews the planned cut, exactly like the optional Claude editor. `local_ai.py` checks whether Ollama runs, which installed models report the `vision` capability, and downloads a model through Ollama on request.

Safeguards for small local models:
- the review schema pins one judgement per strip (min/maxItems, id enum); an incomplete answer is retried once, then reported;
- the review is a checklist (`CHECK_SYSTEM`/`checklist_moment`): overlay frames, opponent, firing, kill, peak, highlight; usability and the event come from those facts and the highlight is half model score, half fixed evidence score;
- judgements are blended 60/40 with the measured activity score (`LOCAL_WEIGHT`), and timing stays measured locally;
- if more than two-thirds of the reviewed clips are flagged as overlays the flags are ignored (the model is misreading the HUD);
- `enforce_playbook` rewrites the director plan to standard montage craft (hook, climax on the drop, motivated transitions, ramp budget, clean ending) and records each correction in `analysis.json → ai_editor.edit_plan.playbook`;
- director chat (`edit_chat.py`) only runs validated actions on topics the person mentioned.

Evaluation (`scratchpad` harness, not shipped): 16 six-frame strips from the held-out Xonotic duel, labelled by inspecting every frame: 5 death/scoreboard, 6 fights (opponent plus fire, some kills), 5 walking/pickups. Metrics: death screens caught, non-death clips flagged unusable, AUC of the model's own highlight for fights vs walking, seconds per strip on this 4-core CPU while other work ran.

| Model / prompt | Deaths | False flags | AUC | s/strip |
|---|---|---|---|---|
| activity heuristic | — | — | 0.63 | — |
| qwen3.5:9b, single judgement | 1/5 | 1 | 0.58 | 63 |
| **qwen3.5:9b, checklist (default)** | 4/5 | 0 | 0.70 | 43 |
| qwen2.5vl:7b, checklist | 0/5 | 0 | 0.70 | 89 |
| gemma4:e4b, checklist | 5/5 | 11 | 0.37 | 25 |

The missed death strip shows the scoreboard in one of six frames, which the checklist rule (two or more overlaid frames) deliberately keeps. 16 strips is a small sample from one game: treat the numbers as a ranking, not a guarantee. Larger models were not measured (disk/RAM here).

# Legacy text-only planner (`--ollama-model`)


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

# Director chat (`edit_chat.py`)

The chat model (local by default) returns a reply plus named actions. Three layers keep it reliable:

1. **Validation**: only known actions with valid values; impossible shots and renders are rejected and shown.
2. **Consent**: an action runs only if the person's message is about that topic (`TOPICS`); "every format" renders need explicit words.
3. **Grounding** (`ground`): explicit values in the person's words win over the model's paraphrase — seconds, pasted links, named looks/paces/styles, named on/off switches (nearest switch word wins), explicit shot commands ("move shot 2 later", "swap shot 3"), and "render it" for an edited timeline. A style is not undone by settings that repeat it.

Scripted evaluation (`scratchpad` harness, not shipped; 24 requests: 12 everyday, 4 shot/style/render skills, 8 harder combined or negated requests; real qwen3.5:9b on a 4-core CPU, ~31 s per request). Each grounding rule was added for a failure observed in these runs and is unit-tested with that exact case. The model is not deterministic, so results vary by one or two requests between runs; see the development log for the run-by-run numbers.
