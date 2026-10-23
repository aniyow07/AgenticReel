# AgentReel reference

Details behind the [README](../README.md): CLI flags, brief fields, how each stage works, AI provider
behaviour, the job folder and gameplay footage provenance.

## CLI

```powershell
# any topic, no YAML needed
.\.venv\Scripts\python.exe run.py --topic "Why do cats purr?" --mode subway --duration 40

# YAML brief (see briefs/examples/)
.\.venv\Scripts\python.exe run.py --brief briefs\examples\procrastination.yaml --seed 42

# quick test render (small, short, labelled TEST in the QA report)
.\.venv\Scripts\python.exe run.py --brief briefs\examples\green_hydrogen.yaml --dev-short --local-only

# render from a supplied script/storyboard (no LLM needed)
.\.venv\Scripts\python.exe run.py --brief briefs\examples\green_hydrogen.yaml --local-only `
    --script-json briefs\examples\green_hydrogen_script.json `
    --storyboard-json briefs\examples\green_hydrogen_storyboard.json

.\.venv\Scripts\python.exe run.py --resume <JOB_ID>      # continue a failed/interrupted job
.\.venv\Scripts\python.exe run.py --rerender <JOB_ID> --highlight-color "#FF3D7F" --caption-position lower
```

| Flag | Meaning |
|---|---|
| `--mode og\|minecraft\|subway` | override the brief's mode |
| `--provider gemini\|openrouter` | AI provider for this run |
| `--local-only` | `LOCAL_ONLY`: no LLM requests at all |
| `--ai-required` | `AI_REQUIRED`: fail clearly if the AI provider is unavailable |
| `--seed N` | reproducible local choices (palette, gameplay cuts, clip order); LLM output may still differ |
| `--voice NAME` | voice id (`--list-voices` lists them) |
| `--voice-speed N` | speaking speed in percent (default +10 from `TTS_RATE`); script length follows it |
| `--tts-engine chatterbox\|edge` | voice engine for this run (default `TTS_ENGINE`) |
| `--gpu auto\|on\|off` | NVENC + Chrome GPU rendering (default `AGENTREEL_GPU`, else `auto`); a failed GPU step is retried on the CPU. `web.py` takes it too |
| `--dev-short` | short 540×960 test render (allowed below 30 s; never labelled production) |
| `--resume JOB_ID` | rerun only stages whose inputs changed or that did not finish |
| `--rerender JOB_ID` | new caption style, same content |
| `--script-json / --storyboard-json` | supply your own validated script/storyboard |
| `--output-dir PATH` | where job folders go (default `outputs/`) |

Exit code: 0 when technical QA passes, 3 when it fails, 2 for an invalid brief.

## Briefs

```yaml
id: demo_001
topic: Why do people procrastinate?        # anything; no fixed topic list
audience: College students
mode: minecraft                            # og | minecraft | subway
duration_s: 45                             # 30-60 for production; shorter only with dev_short: true
tone: engaging, conversational
language: English
subtitle_language: English
format: video_9x16                         # or video_16x9
content_type: factual_explainer            # promotional | awareness | fictional_story | general_entertainment | educational_story | opinion_commentary
must_include: []
must_avoid: []
cta: ""
source_files: [../sources/procrastination_notes.md]   # PDF, DOCX, TXT, MD (relative to the YAML)
source_text: ""                            # optional pasted source text
narration_audio: ""                        # optional: your own narration instead of TTS
music: ""                                  # optional: a track you are licensed to use
```

Every field is validated (Pydantic, `extra="forbid"`) before a job starts.

## How each stage works

* **Grounding.** The Researcher uses only supplied documents/text, plus Wikipedia when
  `ONLINE_RESEARCH=true` (needs `AGENTREEL_CONTACT` for the Wikimedia User-Agent policy). Every claim is
  re-checked against the source text and numbers must appear verbatim in the evidence; unsupported claims are
  blocked by the Scriptwriter and Critic. Without sources, factual videos stay general and say so.
* **Manim templates.** 46 trusted templates in `manim/templates/` (full list in
  [manim/README.md](../manim/README.md)): topic templates (steps, comparisons, data, maths and science,
  computing and security), 15 general ones (ranking, pros/cons, myth vs fact, roadmap, quote card…) and 18
  in 3D. The Storyboarder picks from `agents/template_catalog.py`, ranked by topic and rotated so recent
  videos don't repeat. Each scene gets one of five looks; parameters are validated, never code.
* **Backgrounds** (Remotion, OG mode): 12 animated backdrops chosen per scene to match its mood, never the
  same twice in a row.
* **No generated code runs.** Storyboards are parameters for known Remotion components and Manim
  templates, validated on both sides (Pydantic in Python, Zod in Remotion). Subprocesses use argument lists,
  paths are sanitised, uploads are type- and size-checked (50 MB).
* **Voice and timing.** Chatterbox-Turbo synthesises each narration chunk; its real duration is measured
  with ffprobe and Whisper supplies word timings for captions. Speed is applied afterwards with FFmpeg
  `atempo`; tags like `[laugh]` are performed, never captioned. With `TTS_ENGINE=edge`, Edge word boundaries
  are used; offline, the Windows SAPI voice (no word timings) shares each chunk's measured length among its
  phrases (flagged in QA).
* **Rendering.** Media is hard-linked into the job's `public/` folder; props go in a JSON file and are
  parsed with Zod in `calculateMetadata`. With the GPU on, Remotion uses Chrome's ANGLE backend.
* **Finishing.** Two-pass `loudnorm` to about -14 LUFS, H.264 `yuv420p` (NVENC on the GPU, else libx264),
  AAC 48 kHz stereo, 30 fps, `+faststart`, re-encoded with a computed bitrate above 100 MB.
* **QA and repair.** About 30 checks (codec, resolution, duration, black frames, loudness, captions vs
  narration, scene coverage, gameplay provenance, unsupported claims, must_avoid…). Failures go back to the
  responsible stage, at most `MAX_REPAIR_ATTEMPTS` (default 2) times. A technical pass is reported
  separately from semantic approval, which needs an LLM.
* **Caching and resume.** Each stage stores an input fingerprint in `state.json` and is reused only if it
  finished, its files exist and its inputs are unchanged. TTS chunks and backgrounds are cached by content hash.

## Job folder

```
outputs/<job-id>/
  brief.json brief.yaml state.json plan.json facts.json retrieval_index.json
  script.md script.json storyboard.json captions.json captions.srt render_props.json
  final.mp4 qa_report.json
  inputs/        copied uploads / preset script+storyboard
  public/        Remotion public dir for this job (hard links)
  render/        remotion_raw.mp4, finish.json (loudness, checksum)
  assets/        manifest.json, manifest.csv, audio/, manim/, background_*.mp4
  logs/          run_log.jsonl, cost_report.csv, interventions.md
```

## AI providers

Pick one per run with `--provider`, or set `LLM_PROVIDER` in `.env`. Model lists live in `.env`
(see `.env.example`), not in code.

* **Gemini** (free key from Google AI Studio): `GEMINI_MODEL` then `GEMINI_FALLBACK_MODELS`. Requests are
  paced (`GEMINI_MIN_INTERVAL_S`, 6 s for the free tier), per-minute limits are waited out, and a model whose
  daily quota is used up is skipped until midnight Pacific time.
* **OpenRouter**: `OPENROUTER_MODEL` then `OPENROUTER_FALLBACK_MODELS`. A model is used only if it is free
  per OpenRouter's pricing or `ALLOW_PAID_MODELS=true` (unknown prices count as paid). 429/5xx/timeouts back
  off and retry, then move on; 400/404 move on at once; 401 and 402 stop. A global ledger
  (`outputs/.spend_ledger.json`) enforces `MAX_API_SPEND_USD`.
* **Both**: replies are JSON validated with Pydantic, with one bounded repair prompt per model. Every call
  is logged (model, prompt version, tokens, latency, retries, cost measured or estimated).
  `AGENTREEL_EXECUTION_MODE` is `AI_PREFERRED` (fall back to local templates), `AI_REQUIRED` or `LOCAL_ONLY`.
* The LLM plans, proposes claims, writes, storyboards and reviews; timing, rendering and validation are
  deterministic.

## Gameplay footage

`scripts/setup_gameplay_assets.py` downloads the clips in `assets/gameplay_sources.yaml` (resumable),
validates them (ffprobe, decode test, SHA-256) and records provenance in `assets/manifest.csv`. Brainrot
modes refuse to render without a usable clip of the right game.

| Clip | Source | Status |
|---|---|---|
| `minecraft/parkour.mp4` (1280×720, 363 s) | Internet Archive `il-mio-parkour-su-minecraft-vinci-teo-00-yt` | **needs_review**: states CC0, uploader not independently verified; intro, menus, a death screen and outro excluded |
| `subway/subway_surfers.mp4` (720×1278, 193 s) | Internet Archive `subway-surfers-2024-gameplay-4-k-9x-16-no-copyright-1` | **needs_review**: re-upload of a "No Copyright" compilation, which is not proof of permission |

Before publishing, replace them with footage you recorded or have permission for:

```powershell
python scripts/setup_gameplay_assets.py --game subway --register D:\recordings\my_run.mp4 `
    --creator "me" --license "own recording" --review-status verified --usable-ranges "5-170"
python scripts/setup_gameplay_assets.py --game minecraft --url https://example.com/authorised.mp4 `
    --creator "..." --license "..." --permission-url "..."
python scripts/setup_gameplay_assets.py --status
```

Backgrounds take stretches from the middle 70 % of each usable range, a new one every 4–7 s with short
crossfades, cover-scaled and cropped to the video's format, audio muted.

## Voice setup details

Chatterbox-Turbo needs a newer PyTorch than the main app, so it lives in `.venv-tts`. The override keeps the
CUDA 12.8 build (RTX 50 cards need it; chatterbox-tts pins 2.6). Word timings come from Whisper `small`
(faster-whisper). Voices are the model's built-in voice plus the reference clips in `assets/voices`
(see its README). Tested on an RTX 5050 (8 GB): about 2.9 GB of GPU memory, roughly 3x faster than real
time, about 25 s to load on first use.
