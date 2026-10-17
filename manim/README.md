# Manim templates

Trusted, parameterised Manim Community Edition scenes used by OG mode. The pipeline never runs
LLM-written Python: an agent can only choose one of these templates and fill in parameters, which
`rendering/manim_runner.py` validates with Pydantic before rendering.

| Template | Scene class | Parameters |
|---|---|---|
| `process_diagram.py` | `ProcessDiagramScene` | `title`, `steps` (2–6) |
| `flow_diagram.py` | `FlowDiagramScene` | `title`, `inputs` (1–4), `center`, `outputs` (1–4) |
| `timeline.py` | `TimelineScene` | `title`, `events` (2–6 × `{label, detail}`) |
| `simple_chart.py` | `SimpleChartScene` | `title`, `labels`, `values` (supplied numbers only), `unit` |

All templates also accept `duration_s` (2–20 s, so the clip fits its scene) and an optional
`palette` of hex colours so the clip matches the video's colour scheme. Every template has motion
throughout: drifting ambient shapes, particles flowing along arrows, pulses and live counters.

Only `Text` mobjects are used, so no LaTeX installation is needed (`DecimalNumber`/`MathTex` are
deliberately avoided).

Manual render (parameters come from a JSON file named by an environment variable):

```powershell
$env:AGENTREEL_MANIM_PARAMS = "params.json"   # e.g. {"template": "process_diagram", "title": "...", "steps": ["a", "b"]}
python -m manim render -ql --format=mp4 -r 720,720 manim/templates/process_diagram.py ProcessDiagramScene
# or, with validation and clip location handled for you:
python -m rendering.manim_runner params.json --out outputs/_manim_check
```

If Manim is unavailable or a render fails, the Editor substitutes a compatible Remotion `process`
or `timeline` scene so the OG video still renders, and records why in the job notes and log.
