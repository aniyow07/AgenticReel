# Voices for Chatterbox-Turbo

Every audio clip in this folder becomes a voice in the app's voice picker and in `run.py --list-voices`.
Chatterbox copies the voice of the clip (voice cloning), so use only recordings you have the right to use.

- Format: `.wav`, `.mp3` or `.flac`, **5-20 seconds** (about 10 s is ideal) of one person speaking clearly,
  with no music or background noise.
- The file name is the voice id: lower-case letters, digits, `-` and `_` (for example `maya.wav` -> `maya`).
- Optional `voices.json` gives labels and genders:

```json
{"maya": {"label": "Maya", "gender": "Female"}, "default": {"label": "Built-in"}}
```

`default` is the voice built into the model and is always available.
