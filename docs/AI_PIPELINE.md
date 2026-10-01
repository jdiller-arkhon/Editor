# Local automatic direction with Ollama

## User workflow

Import gameplay, choose music, select Automatic • Ollama, enter the name of an installed local model, optionally enter a short creative brief, then Generate. The engine measures activity, asks Ollama for a bounded plan, fits the timeline to music onsets, mixes any user-supplied dialogue, renders and validates the export. Manual clip selection is not required.

Install Ollama separately from https://ollama.com/download and run a downloaded local model compatible with structured JSON outputs. Use `ollama list` to find model names and `ollama serve` if the local service is not running. Model selection depends on available VRAM/RAM; the app does not download models or provision Ollama. A desktop GPU can help inference, but neither GPU execution nor local model quality has been validated here.

```sh
montage-editor create --gameplay gameplay.mp4 --music song.wav --output exports/ai.mp4 --ollama-model YOUR_INSTALLED_MODEL --brief "Cinematic Christian hope, restraint followed by a confident finish"
```

Without `--ollama-model`, the existing automatic activity engine runs without a model. Desktop defaults to that baseline; choosing Ollama requires a model name. Loaded timeline replay renders stored decisions without another inference request.

## Implemented, experimental scope

Ollama receives up to 120 activity-ranked candidate records with anonymous source IDs, timestamps, source durations and motion/audio scores. No footage, audio, frames or local filenames are sent to the model. It prioritizes candidates, sets global clip-length bounds and chooses cut/black fade/white fade plus duration. The director preserves actual scores, appends unranked candidates and fits non-overlapping source clips to musical onsets. Original requested duration remains the target; limited footage may shorten output. Dialogue remains user-provided and timed; AI settings override manual transition/pacing for new generation.

This is metadata-driven direction, not visual understanding. Models cannot recognize kills, inspect Christianity-related visuals, add absent effects, synthesize dialogue or verify theology. There is no TTS, automatic reference import, speed ramp/compositing renderer, self-improvement loop or studio-quality guarantee.

## Validation boundary and failure behavior

Uses the loopback `/api/chat` endpoint at 127.0.0.1:11434, `stream:false`, JSON Schema format, bounded token budget and a 120-second request timeout. Ignores system proxies and rejects redirects. Choose a downloaded local model; a cloud-backed model configured in Ollama may itself use external inference. No API keys required by this integration.

The app independently validates candidate IDs, duplicates, field allowlist, finite numeric bounds, min/max clip lengths, supported transitions and rationale length. Model output is data only; never executed as commands or accepted as asset paths. It cannot replace source footage or modify export paths. Invalid/unavailable inference produces a clear error and no export; no silent fallback masquerades as AI success. User can explicitly select baseline mode instead.

The `.analysis.json` sidecar records provider, model, validated plan and evidence limitations. Replay persists actual timeline decisions. Rationale is explanatory metadata, not narration or verified fact.

## Tests and evidence

Eight core tests, including mocked structured transport, invalid/duplicate/unknown plan rejection, connection-error behavior and actual MP4 rendering from a mocked director plan. Three desktop checks cover controls, reference artwork and worker behavior. Live Ollama/model inference is not tested in this environment because Ollama is absent. Do not label mocked tests as proof of model quality.

## Official API references

- https://docs.ollama.com/api/chat
- https://docs.ollama.com/capabilities/structured-outputs
- https://docs.ollama.com/api/tags

## Next automation stages — planned

Vision-based event evidence, confidence labeling, voice transcription and timing, licensed dialogue libraries, optional original narration/TTS, advanced effects with measurable controls, automatic output comparison and Windows/GPU performance validation. These require capabilities beyond a text model.
