# Christian storytelling direction

Product goal: studio-quality montages and videos with a deep Christian undertone, making following Christ feel compelling, courageous and contemporary. Visual polish, intelligible dialogue and a coherent message are central to the goal. The current engine is an early implementation; studio quality is a target, not a verified capability.

## Implemented controls

`create --story path/to/story.json` applies user-directed dialogue cues and fades. Existing timeline JSON remains compatible. Render/replay persists the same cues.

```json
{
  "transition": "fade_black",
  "transition_duration": 0.2,
  "dialogue": [
    {
      "source": "C:/EditorAssets/narration.wav",
      "at": 0.5,
      "start": 0,
      "duration": 4,
      "gain": 1,
      "reference": "Original reflection on hope in Christ",
      "text_kind": "original"
    }
  ]
}
```

Use actual local audio recordings. Cue times are seconds in the final montage; source offsets select portions of a recording. Cue bounds must fit the actual generated timeline, including a shortened export. Music is reduced to 25% gain during dialogue and the final mix is limited. Dialogue gain is configurable. Multiple cues may overlap intentionally. This is scheduled ducking, not intelligent voice-sensitive mixing. Fades use black or white, with no clip overlap; `cut` keeps hard cuts. Paths should be absolute; there is no automatic asset search.

Reference and text_kind are provenance metadata, not burned-in captions. Supported kinds: original, paraphrase, quotation. Record Bible translation and verse details for quotations; identify original narration honestly. Import user-recorded narration or authorized clips from sermons, Christian films or other reference media. The application does not supply film/sermon audio, synthesize voices, verify verse quotations or impersonate speakers.

## Creative direction — planned

- Theme briefs: grace, repentance, perseverance, humility, sacrifice, redemption and hope in Christ.
- Narrative arc: struggle → reflection → renewed purpose → invitation. Use original narration or clearly attributed Christian references.
- Quiet openings, purposeful pauses, restrained light imagery, music builds and transitions motivated by the message.
- Pair gameplay with perseverance and discipline carefully; do not automatically portray an in-game kill as divine approval or a spiritual victory.
- End with a sincere invitation to follow Christ rather than equating faith with competitive superiority.
- Future director controls for subtle versus explicit faith emphasis, scripture/caption placement, dialogue selection and user approval of the message.

Example original narration concept: “You don't have to walk alone. Bring the struggle to Christ. Let faith shape your next step.” This is original writing, not a Bible quotation.

## Validation and limits

Integration renders black and white fades, dialogue mixes, timeline roundtrips and full output decode. A frame check confirms the black-fade opening. Artistic quality, dialogue intelligibility on real recordings, automated Christian reference selection and theological accuracy have not been evaluated. A preview/manual editing workflow and real footage evaluation are the next priorities.
