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
| `orbit_3d.py` (3D) | `Orbit3DScene` | `title`, `kind` (atom/planets), `center`, `orbiters` (1–6) |
| `surface_3d.py` (3D) | `Surface3DScene` | `title`, `surface` (paraboloid/saddle/ripple/gaussian/waves/cone), `caption` |
| `bar_chart_3d.py` (3D) | `BarChart3DScene` | `title`, `labels`, `values` (supplied numbers only), `unit` |
| `dna_helix_3d.py` (3D) | `DNAHelix3DScene` | `title`, `caption` |
| `molecule_3d.py` (3D) | `Molecule3DScene` | `title`, `molecule` (water/carbon_dioxide/methane/ammonia/ethylene/benzene/oxygen/ethanol), `caption` |
| `globe_3d.py` (3D) | `Globe3DScene` | `title`, `hubs` (2–6), `caption` |
| `vector_field_3d.py` (3D) | `VectorField3DScene` | `title`, `field` (source/sink/vortex/uniform/dipole/helix), `caption` |
| `crystal_lattice_3d.py` (3D) | `CrystalLattice3DScene` | `title`, `lattice` (simple_cubic/body_centered/face_centered/salt), `caption` |
| `neural_net_3d.py` (3D) | `NeuralNet3DScene` | `title`, `layers` (2–5, input first), `caption` |
| `layer_stack_3d.py` (3D) | `LayerStack3DScene` | `title`, `layers` (2–6, top first), `caption` |
| `planet_layers_3d.py` (3D) | `PlanetLayers3DScene` | `title`, `layers` (2–5, innermost first), `caption` |
| `wave_3d.py` (3D) | `Wave3DScene` | `title`, `kind` (electromagnetic/transverse/standing/longitudinal), `caption` |
| `solids_3d.py` (3D) | `Solids3DScene` | `title`, `shapes` (1–4 named solids) |
| `galaxy_3d.py` (3D) | `Galaxy3DScene` | `title`, `arms` (2–4), `caption` |
| `before_after.py` | `BeforeAfterScene` | `title`, `mode` (versus/before_after), `left_title`, `right_title`, `left_points`/`right_points` (0–4), `verdict` |
| `domino_chain.py` | `DominoChainScene` | `title`, `links` (2–6 causes in order), `effect` |
| `stat_reveal.py` | `StatRevealScene` | `title`, `value` (supplied numbers only), `prefix`, `suffix`, `label`, `style` (counter/ring/dots) |
| `quote_card.py` | `QuoteCardScene` | `title`, `quote` (must be in the sources), `author`, `highlight` |
| `pros_cons.py` | `ProsConsScene` | `title`, `pros`, `cons` (1–4 each), `verdict` (pros/cons/even), `pros_label`, `cons_label` |
| `ranking.py` | `RankingScene` | `title`, `items` (2–6, first is #1), `values` (optional, supplied numbers only), `unit` |
| `funnel.py` | `FunnelScene` | `title`, `stages` (2–5, widest first), `values` (optional, supplied numbers only), `unit` |
| `myth_fact.py` | `MythFactScene` | `title`, `pairs` (1–3 × `{myth, fact}`) |
| `spotlight.py` | `SpotlightScene` | `title`, `words` (3–8), `focus` (one of the words), `caption` |
| `roadmap.py` | `RoadmapScene` | `title`, `stops` (2–6), `goal` |
| `decision_tree.py` | `DecisionTreeScene` | `title`, `question`, `options` (2–3 × `{choice, outcome}`), `picked` |
| `carousel_3d.py` (3D) | `Carousel3DScene` | `title`, `items` (3–6), `caption` |
| `podium_3d.py` (3D) | `Podium3DScene` | `title`, `places` (2–3, first place first), `caption` |
| `cube_faces_3d.py` (3D) | `CubeFaces3DScene` | `title`, `faces` (2–5; the fifth goes on top), `caption` |
| `spiral_timeline_3d.py` (3D) | `SpiralTimeline3DScene` | `title`, `events` (2–6, earliest first), `caption` |

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

The 3D templates take only names from fixed lists, short labels and captions: shapes, molecules,
lattices and fields are built into the template, never supplied as numbers or code. A video uses at most
two 3D scenes (`MAX_3D_SCENES` in `agents/storyboarder.py`).

The general templates (from `before_after` to `spiral_timeline_3d`, listed in `GENERAL` in
`rendering/manim_runner.py`) fit almost any topic. Their text is checked like other on-screen text: any number
or year must appear in the sources or narration, chart-like values must be in the supported facts, and a
`quote_card` quotation must be in the sources with a speaker they name. If Manim cannot render one, the Editor
shows the same data as a Remotion comparison, stat, process, timeline or key-points scene instead.
