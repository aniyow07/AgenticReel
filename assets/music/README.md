# Music

AgentReel ships with no music. Add only tracks you have the right to use (your own, or a licence
that allows editing and redistribution in your videos), then attach them per job:

- UI: "Optional licensed music" upload.
- CLI/YAML brief: `music: path/to/track.mp3`.

Music is looped under the narration and ducked automatically while someone is speaking; the final
mix is normalised to about -14 LUFS. Game audio from gameplay clips is always muted.
