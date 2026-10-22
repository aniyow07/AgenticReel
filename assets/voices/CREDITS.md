# Voice clip credits

The reference clips in this folder are 13-15 s excerpts (a few sentences joined, loudness-normalised) from
**LibriTTS-R** (Koizumi et al., 2023), test-clean split, licensed **CC BY 4.0**
(https://www.openslr.org/141/, fetched through https://huggingface.co/datasets/mythicinfinity/libritts_r).
LibriTTS-R is a restored version of LibriTTS, which is built from **LibriVox** audiobook recordings that their
readers released into the **public domain**. The names below are labels chosen for the app, not the readers' names.

| File | Picker name | LibriTTS speaker | Utterances used |
|---|---|---|---|
| atlas.wav | Atlas · deep storyteller | 7729 | 7729_102255_000002_000005, _000002_000010, _000003_000000 |
| kai.wav | Kai · calm, low, soft-spoken | 1089 | 1089_134691_000002_000001, _000002_000002, _000006_000000 |
| jack.wav | Jack · lively and energetic | 908 | 908_157963_000026_000001, _000004_000000 |
| grace.wav | Grace · warm and steady | 8555 | 8555_284449_000007_000000, _000007_000001 |
| zoe.wav | Zoe · bright and upbeat | 4970 | 4970_29095_000006_000000, _000031_000000, _000040_000002, _000042_000000 |
| nora.wav | Nora · expressive | 121 | 121_121726_000025_000001, _000034_000001, _000005_000001 |

Voices were picked for being different from each other by measured pitch, pitch movement and brightness.
Genders in voices.json are inferred from pitch.

## Japanese-accent voices

`ren.wav`, `haruto.wav`, `yuki.wav` and `sakura.wav` are not recordings of people. They were made on 2026-10-21
by having Microsoft Edge's Japanese text-to-speech voices read an English paragraph, so they speak English with
a Japanese accent, and Chatterbox then clones that sound. Ren and Haruto come from `ja-JP-KeitaNeural` (Haruto
with lower pitch and slower pace); Yuki and Sakura come from `ja-JP-NanamiNeural` (Sakura with higher pitch and
faster pace). They are fine for this personal, non-commercial project; check Microsoft's terms before using them
commercially.
