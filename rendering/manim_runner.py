"""Runs trusted, parameterised Manim templates and stages the clips for Remotion.

Only templates registered in TEMPLATES can run. Parameters are validated with
Pydantic, written to a JSON file and passed to the template through an
environment variable; nothing from an LLM is ever executed as code.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from rendering.media_utils import MediaError, probe, run, sha256

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "manim" / "templates"

Short = Field(min_length=1, max_length=80)
LOOKS = ("rounded", "pill", "sharp", "glass", "underline")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
PALETTE_KEYS = {"background", "surface", "primary", "accent", "text", "mutedText"}


class _Base(BaseModel):
    # colours only (validated hex); lets each clip match the palette of the video around it
    palette: dict[str, str] | None = None
    # card shape and title style; set per scene by the asset generator so diagrams do not all look alike
    look: Literal["rounded", "pill", "sharp", "glass", "underline"] | None = None

    @field_validator("palette")
    @classmethod
    def _palette(cls, v):
        if v is None:
            return v
        bad = [k for k, c in v.items() if k not in PALETTE_KEYS or not _HEX.match(str(c))]
        if bad:
            raise ValueError(f"invalid palette entries: {bad}")
        return v


class ProcessParams(_Base):
    template: Literal["process_diagram"] = "process_diagram"
    title: str = Field(default="", max_length=80)
    steps: list[str] = Field(min_length=2, max_length=6)
    duration_s: float = Field(default=6.0, ge=2, le=20)

    @field_validator("steps")
    @classmethod
    def _steps(cls, v):
        v = [s.strip() for s in v if s.strip()]
        if len(v) < 2:
            raise ValueError("need at least two non-empty steps")
        return [s[:80] for s in v]


class FlowParams(_Base):
    template: Literal["flow_diagram"] = "flow_diagram"
    title: str = Field(default="", max_length=80)
    inputs: list[str] = Field(min_length=1, max_length=4)
    center: str = Short
    outputs: list[str] = Field(min_length=1, max_length=4)
    duration_s: float = Field(default=6.0, ge=2, le=20)


class TimelineEvent(BaseModel):
    label: str = Short
    detail: str = Field(default="", max_length=80)


class TimelineParams(_Base):
    template: Literal["timeline"] = "timeline"
    title: str = Field(default="", max_length=80)
    events: list[TimelineEvent] = Field(min_length=2, max_length=6)
    duration_s: float = Field(default=6.0, ge=2, le=20)


class ChartParams(_Base):
    template: Literal["simple_chart"] = "simple_chart"
    title: str = Field(default="", max_length=80)
    labels: list[str] = Field(min_length=1, max_length=8)
    values: list[float] = Field(min_length=1, max_length=8)
    unit: str = Field(default="", max_length=12)
    duration_s: float = Field(default=6.0, ge=2, le=20)

    @field_validator("values")
    @classmethod
    def _finite(cls, v):
        if any(x != x or x in (float("inf"), float("-inf")) or x < 0 for x in v):
            raise ValueError("values must be finite and non-negative")
        return v

    def model_post_init(self, _ctx) -> None:
        if len(self.labels) != len(self.values):
            raise ValueError("labels and values must have the same length")


class EquationParams(_Base):
    """Math worked step by step: each line is the whole equation after one step (plain text, x^2 allowed)."""
    template: Literal["equation_steps"] = "equation_steps"
    title: str = Field(default="", max_length=80)
    lines: list[str] = Field(min_length=2, max_length=6)
    notes: list[str] = Field(default_factory=list, max_length=5)  # what changed between line i and i+1
    duration_s: float = Field(default=7.0, ge=2, le=20)

    @field_validator("lines")
    @classmethod
    def _lines(cls, v):
        v = [s.strip() for s in v if s.strip()]
        if len(v) < 2:
            raise ValueError("need at least two equation lines")
        if any(len(s) > 48 for s in v):
            raise ValueError("equation lines must be 48 characters or fewer")
        return v

    @field_validator("notes")
    @classmethod
    def _notes(cls, v):
        return [s.strip()[:32] for s in v]


class ReactionParams(_Base):
    """A chemical reaction: formulas like "2H2", "O2" -> "2H2O" (digits become subscripts)."""
    template: Literal["chemical_reaction"] = "chemical_reaction"
    title: str = Field(default="", max_length=80)
    reactants: list[str] = Field(min_length=1, max_length=4)
    products: list[str] = Field(min_length=1, max_length=4)
    condition: str = Field(default="", max_length=24)  # e.g. "heat", "sunlight", "catalyst"
    duration_s: float = Field(default=7.0, ge=2, le=20)

    @field_validator("reactants", "products")
    @classmethod
    def _formulas(cls, v):
        v = [s.strip() for s in v if s.strip()]
        if not v:
            raise ValueError("need at least one formula")
        bad = [s for s in v if len(s) > 20 or not re.fullmatch(r"[0-9A-Za-z()\[\]\^+\-· ]+", s)]
        if bad:
            raise ValueError(f"not chemical formulas: {bad}")
        return v


class ArrayAlgoParams(_Base):
    """Sorting or searching on a small list of numbers; the template runs the algorithm itself."""
    template: Literal["array_algorithm"] = "array_algorithm"
    title: str = Field(default="", max_length=80)
    algorithm: Literal["bubble_sort", "selection_sort", "insertion_sort", "linear_search", "binary_search"]
    values: list[int] = Field(min_length=3, max_length=8)
    target: int | None = None
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("values")
    @classmethod
    def _small(cls, v):
        if any(x < 0 or x > 999 for x in v):
            raise ValueError("values must be between 0 and 999")
        return v

    def model_post_init(self, _ctx) -> None:
        if self.algorithm.endswith("_search") and self.target is None:
            raise ValueError("searches need a target")


class AgentLoopParams(_Base):
    """An AI agent's loop: goal -> steps in a cycle (plan, act, observe ...) -> result, with its tools."""
    template: Literal["agent_loop"] = "agent_loop"
    title: str = Field(default="", max_length=80)
    goal: str = Field(default="", max_length=60)
    agent: str = Field(default="Agent", max_length=24)
    steps: list[str] = Field(min_length=2, max_length=6)
    tools: list[str] = Field(default_factory=list, max_length=4)
    result: str = Field(default="", max_length=40)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("steps", "tools")
    @classmethod
    def _short(cls, v):
        return [s.strip()[:24] for s in v if s.strip()]


class SecurityParams(_Base):
    """A cyberattack and the defence in its way: blocked (bounces off) or breached (alert at the target)."""
    template: Literal["security_flow"] = "security_flow"
    title: str = Field(default="", max_length=80)
    attacker: str = Field(default="Attacker", max_length=24)
    attack: str = Field(default="", max_length=32)
    defense: str = Field(default="", max_length=24)
    target: str = Field(default="Server", max_length=24)
    outcome: Literal["blocked", "breached"] = "blocked"
    encrypted: bool = False
    duration_s: float = Field(default=8.0, ge=2, le=20)


_EXPR_FUNCS = {"sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs"}


def check_expr(text: str) -> str:
    """Accept only plain math in x (numbers, + - * / ^, a few functions, pi, e). Parsed, never run."""
    import ast
    src = str(text).replace("^", "**").replace("−", "-").replace("×", "*")
    if len(src) > 60:
        raise ValueError("function is too long")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"not a valid function: {text!r}") from e
    for n in ast.walk(tree):
        ok = isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
                            ast.USub, ast.UAdd, ast.Load)) \
            or (isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)) \
            or (isinstance(n, ast.Name) and n.id in {"x", "pi", "e"} | _EXPR_FUNCS) \
            or (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _EXPR_FUNCS
                and len(n.args) == 1 and not n.keywords)
        if not ok:
            raise ValueError(f"not allowed in a function: {text!r}")
    return text


class PlotFunction(BaseModel):
    expr: str = Field(min_length=1, max_length=60)
    label: str = Field(default="", max_length=30)

    @field_validator("expr")
    @classmethod
    def _expr(cls, v):
        return check_expr(v)


class FunctionPlotParams(_Base):
    """Graph of y = f(x): 1-3 functions on shared axes, optional marked x values (roots, maxima)."""
    template: Literal["function_plot"] = "function_plot"
    title: str = Field(default="", max_length=80)
    functions: list[PlotFunction] = Field(min_length=1, max_length=3)
    x_min: float = -5
    x_max: float = 5
    y_min: float | None = None
    y_max: float | None = None
    mark_x: list[float] = Field(default_factory=list, max_length=3)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    def model_post_init(self, _ctx) -> None:
        if not (-1e4 <= self.x_min < self.x_max <= 1e4):
            raise ValueError("x range must be increasing and reasonable")


class Series(BaseModel):
    name: str = Field(default="", max_length=20)
    values: list[float] = Field(min_length=2, max_length=10)


class LineChartParams(_Base):
    """Values over time or categories, 1-3 series (numbers must come from supported facts)."""
    template: Literal["line_chart"] = "line_chart"
    title: str = Field(default="", max_length=80)
    labels: list[str] = Field(min_length=2, max_length=10)
    series: list[Series] = Field(min_length=1, max_length=3)
    unit: str = Field(default="", max_length=12)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    def model_post_init(self, _ctx) -> None:
        if any(len(s.values) != len(self.labels) for s in self.series):
            raise ValueError("every series needs one value per label")


class PieChartParams(_Base):
    """Shares of a whole as a donut (numbers must come from supported facts)."""
    template: Literal["pie_chart"] = "pie_chart"
    title: str = Field(default="", max_length=80)
    labels: list[str] = Field(min_length=2, max_length=6)
    values: list[float] = Field(min_length=2, max_length=6)
    unit: str = Field(default="", max_length=12)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("values")
    @classmethod
    def _positive(cls, v):
        if any(x != x or x < 0 for x in v) or sum(v) <= 0:
            raise ValueError("values must be non-negative with a positive total")
        return v

    def model_post_init(self, _ctx) -> None:
        if len(self.labels) != len(self.values):
            raise ValueError("labels and values must have the same length")


class NodeGraphParams(_Base):
    """Nodes and edges (networks, graph algorithms, neural nets); a pulse follows `path`."""
    template: Literal["node_graph"] = "node_graph"
    title: str = Field(default="", max_length=80)
    nodes: list[str] = Field(min_length=2, max_length=10)
    edges: list[list[str | int]] = Field(default_factory=list, max_length=24)
    path: list[str | int] = Field(default_factory=list, max_length=10)
    directed: bool = False
    layers: list[int] = Field(default_factory=list, max_length=5)  # e.g. [3, 4, 2] lays nodes out as a network
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("edges")
    @classmethod
    def _pairs(cls, v):
        if any(len(e) != 2 for e in v):
            raise ValueError("each edge is a pair of node names")
        return v


def _items(v: list[str], lo: int, hi: int, what: str) -> list[str]:
    v = [str(s).strip()[:40] for s in v if str(s).strip()]
    if not lo <= len(v) <= hi:
        raise ValueError(f"need {lo}-{hi} {what}")
    return v


class CycleParams(_Base):
    """Stages that repeat in a loop (water cycle, product life cycle, a feedback loop)."""
    template: Literal["cycle_diagram"] = "cycle_diagram"
    title: str = Field(default="", max_length=80)
    stages: list[str]
    center: str = Field(default="", max_length=30)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("stages")
    @classmethod
    def _stages(cls, v):
        return _items(v, 3, 6, "stages")


class VennSet(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    items: list[str] = Field(default_factory=list, max_length=3)


class VennParams(_Base):
    """Two or three overlapping groups and what they share."""
    template: Literal["venn_diagram"] = "venn_diagram"
    title: str = Field(default="", max_length=80)
    sets: list[VennSet] = Field(min_length=2, max_length=3)
    shared: list[str] = Field(default_factory=list, max_length=3)
    duration_s: float = Field(default=8.0, ge=2, le=20)


class PyramidParams(_Base):
    """A hierarchy, top level first (Maslow, food chain, OSI layers, priorities)."""
    template: Literal["pyramid"] = "pyramid"
    title: str = Field(default="", max_length=80)
    levels: list[str]
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("levels")
    @classmethod
    def _levels(cls, v):
        return _items(v, 2, 6, "levels")


class Branch(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    items: list[str] = Field(default_factory=list, max_length=2)


class MindMapParams(_Base):
    """A central idea with 2-6 branches and up to two leaves each."""
    template: Literal["mind_map"] = "mind_map"
    title: str = Field(default="", max_length=80)
    center: str = Field(min_length=1, max_length=30)
    branches: list[Branch] = Field(min_length=2, max_length=6)
    duration_s: float = Field(default=8.0, ge=2, le=20)


TEMPLATES: dict[str, tuple[str, str, type[BaseModel]]] = {
    "cycle_diagram": ("cycle_diagram.py", "CycleDiagramScene", CycleParams),
    "venn_diagram": ("venn_diagram.py", "VennDiagramScene", VennParams),
    "pyramid": ("pyramid.py", "PyramidScene", PyramidParams),
    "mind_map": ("mind_map.py", "MindMapScene", MindMapParams),
    "function_plot": ("function_plot.py", "FunctionPlotScene", FunctionPlotParams),
    "line_chart": ("line_chart.py", "LineChartScene", LineChartParams),
    "pie_chart": ("pie_chart.py", "PieChartScene", PieChartParams),
    "node_graph": ("node_graph.py", "NodeGraphScene", NodeGraphParams),
    "array_algorithm": ("array_algorithm.py", "ArrayAlgorithmScene", ArrayAlgoParams),
    "agent_loop": ("agent_loop.py", "AgentLoopScene", AgentLoopParams),
    "security_flow": ("security_flow.py", "SecurityFlowScene", SecurityParams),
    "process_diagram": ("process_diagram.py", "ProcessDiagramScene", ProcessParams),
    "flow_diagram": ("flow_diagram.py", "FlowDiagramScene", FlowParams),
    "timeline": ("timeline.py", "TimelineScene", TimelineParams),
    "simple_chart": ("simple_chart.py", "SimpleChartScene", ChartParams),
    "equation_steps": ("equation_steps.py", "EquationStepsScene", EquationParams),
    "chemical_reaction": ("chemical_reaction.py", "ChemicalReactionScene", ReactionParams),
}

QUALITY = {"dev": ("-ql", 15), "prod": ("-qm", 30)}


class ManimResult(BaseModel):
    ok: bool
    template: str
    clip_path: str | None = None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    returncode: int | None = None
    elapsed_s: float = 0
    error: str | None = None
    log_tail: str = ""


def manim_executable() -> list[str] | None:
    """Prefer the manim in this interpreter's environment."""
    try:
        import manim  # noqa: F401
        return [sys.executable, "-m", "manim"]
    except ImportError:
        exe = shutil.which("manim")
        return [exe] if exe else None


def is_available() -> bool:
    return manim_executable() is not None


def validate(params: dict) -> BaseModel:
    name = params.get("template")
    if name not in TEMPLATES:
        raise ValueError(f"unknown Manim template: {name!r}")
    return TEMPLATES[name][2].model_validate(params)


def render(params: dict, out_dir: Path, name: str, quality: str = "dev", size: tuple[int, int] = (720, 720),
           timeout: float = 300, transparent: bool = False) -> ManimResult:
    """transparent=True renders a VP9 WebM with an alpha channel so the diagram floats over the video's own
    animated background instead of sitting in a dark box."""
    """Render one clip to out_dir/<name>.mp4 and validate it with ffprobe."""
    template = str(params.get("template"))
    t0 = time.time()
    try:
        model = validate(params)
    except Exception as e:  # pydantic.ValidationError or ValueError
        return ManimResult(ok=False, template=template, error=f"invalid parameters: {e}")
    cmd_base = manim_executable()
    if not cmd_base:
        return ManimResult(ok=False, template=template, error="Manim is not installed")

    file_name, scene_cls, _ = TEMPLATES[template]
    out_dir = Path(out_dir).resolve()
    work = out_dir / f"_{name}_work"
    work.mkdir(parents=True, exist_ok=True)
    params_file = work / "params.json"
    params_file.write_text(model.model_dump_json(), encoding="utf-8")
    qflag, fps = QUALITY.get(quality, QUALITY["dev"])
    w, h = size
    ext = "webm" if transparent else "mp4"
    cmd = [*cmd_base, "render", qflag, f"--format={ext}", *(["-t"] if transparent else []), "--disable_caching",
           "--fps", str(fps),
           "-r", f"{w},{h}", "--media_dir", str(work / "media"), "-o", name,
           str(TEMPLATE_DIR / file_name), scene_cls]
    env = {**os.environ, "AGENTREEL_MANIM_PARAMS": str(params_file), "PYTHONIOENCODING": "utf-8"}
    try:
        cp = run(cmd, timeout=timeout, cwd=work, env=env)
    except Exception as e:
        return ManimResult(ok=False, template=template, error=f"manim did not finish: {e}",
                           elapsed_s=time.time() - t0)
    tail = (cp.stdout + "\n" + cp.stderr)[-3000:]
    if cp.returncode != 0:
        return ManimResult(ok=False, template=template, returncode=cp.returncode, error="manim exited with an error",
                           log_tail=tail, elapsed_s=time.time() - t0)
    produced = sorted((work / "media").rglob(f"{name}.{ext}"), key=lambda p: p.stat().st_mtime)
    if not produced:
        return ManimResult(ok=False, template=template, returncode=cp.returncode,
                           error="manim reported success but no clip was found", log_tail=tail,
                           elapsed_s=time.time() - t0)
    final = out_dir / f"{name}.{ext}"
    shutil.move(str(produced[-1]), final)
    shutil.rmtree(work, ignore_errors=True)
    try:
        info = probe(final)
    except MediaError as e:
        return ManimResult(ok=False, template=template, error=str(e), log_tail=tail, elapsed_s=time.time() - t0)
    if not info.has_video or info.duration <= 0:
        return ManimResult(ok=False, template=template, error="clip has no playable video stream",
                           elapsed_s=time.time() - t0)
    return ManimResult(ok=True, template=template, clip_path=str(final), duration_s=info.duration,
                       width=info.width, height=info.height, sha256=sha256(final), returncode=0,
                       elapsed_s=time.time() - t0, log_tail=tail[-800:])


if __name__ == "__main__":  # manual check: python -m rendering.manim_runner
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("params_json")
    ap.add_argument("--out", default="outputs/_manim_check")
    a = ap.parse_args()
    res = render(json.loads(Path(a.params_json).read_text(encoding="utf-8")), Path(a.out), "clip")
    print(res.model_dump_json(indent=2))

