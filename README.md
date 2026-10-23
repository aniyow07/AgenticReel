# AgentReel

AgentReel turns any topic or brief into a finished short video. Seven AI agents plan, research, write,
storyboard, voice, edit and check it, and every claim is grounded in your sources.

| Style | What you get |
|---|---|
| **Motion graphics (OG)** | Animated explainer: titles, key points, stats, timelines, charts from your data and Manim animations (2D and 3D) on animated backgrounds |
| **Minecraft Brainrot** | Real Minecraft parkour gameplay with narration and big word-synced captions |
| **Subway Brainrot** | Real Subway Surfers gameplay with the same caption engine and its own theme |

Highlights:

- **Local voice.** Narration from Chatterbox-Turbo running on your GPU, with Whisper word timings for captions.
- **Grounded facts.** Answers come from your PDFs, DOCX, TXT or MD files (and optionally Wikipedia); unsupported claims are blocked.
- **46 Manim templates.** Topic templates, 15 general ones and 18 in 3D, picked to fit each video. No generated code is ever run.
- **GPU rendering.** Remotion and FFmpeg (NVENC) use an NVIDIA GPU when one works, and the CPU otherwise.
- **Self-checking.** About 30 QA checks, with failures sent back to the stage that caused them.

A step-by-step guide is in [docs/AgentReel_Guide.pdf](docs/AgentReel_Guide.pdf); flags, brief fields and
internals are in [docs/reference.md](docs/reference.md).

## Architecture

![AgentReel architecture](docs/architecture.png)

Python orchestrates seven agents with schema-checked hand-offs. Remotion composes every video, Manim renders
animation clips for it, and FFmpeg finishes and validates the result. The diagram's text version is
[docs/architecture.mmd](docs/architecture.mmd); redraw the image with `python scripts/draw_architecture.py`.

| # | Agent | Output |
|---|---|---|
| 1 | Planner | `plan.json`: scenes, Manim beats, research needs |
| 2 | Researcher (RAG) | `facts.json`: claims with source, page and evidence |
| 3 | Scriptwriter | `script.json`: lines that cite facts |
| 4 | Storyboarder | `storyboard.json`: visuals and templates per scene |
| 5 | Asset Generator | voice, Manim clips, gameplay background, asset manifest |
| 6 | Editor | `render_props.json`, captions, `final.mp4` |
| 7 | Critic / QA | `qa_report.json` |

Every agent has a local fallback, so `--local-only` works with no API at all (with simpler scripts).

## Setup (Windows)

Tested on Windows 11 with Python 3.12, Node 22, FFmpeg 9.0, Remotion 4.0 and Manim CE 0.22. FFmpeg and Node
must be on `PATH`. No Docker, LaTeX or paid API is needed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd remotion; npm install; cd ..
copy .env.example .env                                         # add GEMINI_API_KEY and/or OPENROUTER_API_KEY
.\.venv\Scripts\python.exe scripts\setup_gameplay_assets.py    # fetches the gameplay clips (Brainrot styles)
.\.venv\Scripts\python.exe run.py --status                     # checks the toolchain
```

**Local voice.** Chatterbox-Turbo lives in its own environment, `.venv-tts`, because it needs a newer PyTorch:

```powershell
uv venv .venv-tts --python 3.12
uv pip install --python .venv-tts\Scripts\python.exe torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
"torch==2.8.0+cu128`ntorchaudio==2.8.0+cu128" | Out-File -Encoding ascii tts-override.txt
uv pip install --python .venv-tts\Scripts\python.exe chatterbox-tts==0.1.7 faster-whisper --override tts-override.txt --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
# model: every file of huggingface.co/ResembleAI/chatterbox-turbo except s3gen.safetensors, into models\chatterbox-turbo
```

The older Microsoft voices are still available as **Classic** in the voice picker (or `TTS_ENGINE=edge`); they need internet.

Not in the repository: your `.env`, generated videos (`outputs/`), the gameplay footage (fetched locally because
its licence is unverified) and the Chatterbox model.

## Run

**Web app** (main UI, opens http://127.0.0.1:8600):

```powershell
.\.venv\Scripts\python.exe web.py                     # --provider gemini|openrouter, --port, --gpu, --no-browser
```

Four screens: Create, Rendering (live progress), Result (player, downloads, new versions in another style or
voice that reuse the script) and Library. The server uses only the Python standard library (`webapp/`) and the
UI is plain ES modules (`webui/`), so there is no build step. It listens on 127.0.0.1 only.

**CLI:**

```powershell
.\.venv\Scripts\python.exe run.py --topic "Why do cats purr?" --mode subway --duration 40
.\.venv\Scripts\python.exe run.py --brief briefs\examples\procrastination.yaml
.\.venv\Scripts\python.exe run.py --resume <JOB_ID>
```

All flags and the brief format are in [docs/reference.md](docs/reference.md). The older Streamlit UI still
works with `python -m streamlit run app.py`.

## AI providers

Use **Gemini** (free key from Google AI Studio) or **OpenRouter**. Set keys and models in `.env`, and choose with
`--provider` or `LLM_PROVIDER`. Requests are paced and retried, fall back through a model list, and OpenRouter
spending is capped by `MAX_API_SPEND_USD`. `AGENTREEL_EXECUTION_MODE` picks `AI_PREFERRED` (default),
`AI_REQUIRED` or `LOCAL_ONLY`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not slow"   # fast tests, API calls mocked
.\.venv\Scripts\python.exe -m pytest -m slow         # real Manim + Remotion + FFmpeg renders
cd remotion; npx vitest run; npx tsc --noEmit
```

## Known limitations

- Free AI tiers run out (OpenRouter about 50 requests a day, Gemini's main model about 20), and the backup
  model writes shorter scripts.
- Without an LLM, scripts are honest but generic; supply sources or your own `--script-json` for better results.
- Both bundled gameplay clips are `needs_review` for licensing. Replace them before publishing
  ([details](docs/reference.md#gameplay-footage)).
- Chatterbox-Turbo is English only and slow without an NVIDIA GPU.
- Wikipedia research is off by default (`ONLINE_RESEARCH=true`, plus `AGENTREEL_CONTACT`).
