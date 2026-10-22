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
    algorithm: Literal["bubble_sort", "selection_sort", "insertion_sort", "quick_sort", "linear_search",
                       "binary_search"]
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


class Orbit3DParams(_Base):
    """3D: bodies circling a centre on tilted rings (atom with electrons, or a star with planets)."""
    template: Literal["orbit_3d"] = "orbit_3d"
    title: str = Field(default="", max_length=80)
    kind: Literal["atom", "planets"] = "atom"
    center: str = Field(default="", max_length=24)
    orbiters: list[str]
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("orbiters")
    @classmethod
    def _orbiters(cls, v):
        return [s[:20] for s in _items(v, 1, 6, "orbiters")]


class Surface3DParams(_Base):
    """3D: a named surface z = f(x, y) rising out of the floor while the camera circles it."""
    template: Literal["surface_3d"] = "surface_3d"
    title: str = Field(default="", max_length=80)
    surface: Literal["paraboloid", "saddle", "ripple", "gaussian", "waves", "cone"] = "paraboloid"
    caption: str = Field(default="", max_length=40)
    duration_s: float = Field(default=8.0, ge=2, le=20)


class BarChart3DParams(PieChartParams):
    """3D: solid bars rising from a floor grid (numbers must come from supported facts)."""
    template: Literal["bar_chart_3d"] = "bar_chart_3d"  # type: ignore[assignment]
    labels: list[str] = Field(min_length=2, max_length=8)
    values: list[float] = Field(min_length=2, max_length=8)


class _Scene3D(_Base):
    title: str = Field(default="", max_length=80)
    caption: str = Field(default="", max_length=40)
    duration_s: float = Field(default=8.0, ge=2, le=20)


class _Layers3D(_Scene3D):
    layers: list[str]

    @field_validator("layers")
    @classmethod
    def _layers(cls, v):
        return [s[:24] for s in _items(v, 2, 6, "layers")]


class DNAHelix3DParams(_Scene3D):
    """3D: a turning double helix the camera climbs."""
    template: Literal["dna_helix_3d"] = "dna_helix_3d"


class Molecule3DParams(_Scene3D):
    """3D: ball-and-stick model of a named molecule (coordinates are built in, never supplied)."""
    template: Literal["molecule_3d"] = "molecule_3d"
    molecule: Literal["water", "carbon_dioxide", "methane", "ammonia", "ethylene", "benzene", "oxygen",
                      "ethanol"] = "water"


class Globe3DParams(_Scene3D):
    """3D: a spinning wireframe globe with arcs and packets travelling between named hubs."""
    template: Literal["globe_3d"] = "globe_3d"
    hubs: list[str]

    @field_validator("hubs")
    @classmethod
    def _hubs(cls, v):
        return [s[:20] for s in _items(v, 2, 6, "hubs")]


class VectorField3DParams(_Scene3D):
    """3D: arrows of a named field shape with a test particle following it."""
    template: Literal["vector_field_3d"] = "vector_field_3d"
    field: Literal["source", "sink", "vortex", "uniform", "dipole", "helix"] = "source"


class CrystalLattice3DParams(_Scene3D):
    """3D: a named crystal lattice the camera pulls out of."""
    template: Literal["crystal_lattice_3d"] = "crystal_lattice_3d"
    lattice: Literal["simple_cubic", "body_centered", "face_centered", "salt"] = "simple_cubic"


class NeuralNet3DParams(_Layers3D):
    """3D: layers of neurons with signals pulsing through, the camera flying along the network."""
    template: Literal["neural_net_3d"] = "neural_net_3d"

    @field_validator("layers")
    @classmethod
    def _layers(cls, v):
        return [s[:24] for s in _items(v, 2, 5, "layers")]


class LayerStack3DParams(_Layers3D):
    """3D: named slabs drop into a stack (top layer first) and then pull apart in an exploded view."""
    template: Literal["layer_stack_3d"] = "layer_stack_3d"


class PlanetLayers3DParams(_Layers3D):
    """3D: nested shells (innermost first) peeled away one by one as the camera moves in."""
    template: Literal["planet_layers_3d"] = "planet_layers_3d"

    @field_validator("layers")
    @classmethod
    def _layers(cls, v):
        return [s[:24] for s in _items(v, 2, 5, "layers")]


class Wave3DParams(_Scene3D):
    """3D: a named kind of travelling wave, seen side-on and then from an angle."""
    template: Literal["wave_3d"] = "wave_3d"
    kind: Literal["electromagnetic", "transverse", "standing", "longitudinal"] = "transverse"


SOLIDS = ("cube", "tetrahedron", "octahedron", "dodecahedron", "icosahedron", "sphere", "cylinder", "cone", "torus")


class Solids3DParams(_Scene3D):
    """3D: named solid shapes spin in and swap one after another."""
    template: Literal["solids_3d"] = "solids_3d"
    shapes: list[Literal["cube", "tetrahedron", "octahedron", "dodecahedron", "icosahedron", "sphere", "cylinder",
                         "cone", "torus"]] = Field(min_length=1, max_length=4)


class Galaxy3DParams(_Scene3D):
    """3D: a spiral galaxy of stars the camera swoops over, from face-on to edge-on."""
    template: Literal["galaxy_3d"] = "galaxy_3d"
    arms: int = Field(default=2, ge=2, le=4)


# ---------------- general templates: they fit almost any topic ----------------
def _short_list(v: list[str], lo: int, hi: int, what: str, n: int = 40) -> list[str]:
    return [s[:n] for s in _items(v, lo, hi, what)]


def _numbers(v: list[float]) -> list[float]:
    if any(x != x or x in (float("inf"), float("-inf")) or x < 0 for x in v):
        raise ValueError("values must be finite and non-negative")
    return v


class BeforeAfterParams(_Base):
    """Two things side by side ("versus") or one thing changing ("before_after"), with up to four points each."""
    template: Literal["before_after"] = "before_after"
    title: str = Field(default="", max_length=80)
    mode: Literal["versus", "before_after"] = "versus"
    left_title: str = Field(default="", max_length=24)
    right_title: str = Field(default="", max_length=24)
    left_points: list[str] = Field(default_factory=list, max_length=4)
    right_points: list[str] = Field(default_factory=list, max_length=4)
    verdict: str = Field(default="", max_length=40)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("left_points", "right_points")
    @classmethod
    def _points(cls, v):
        return [s.strip()[:40] for s in v if s.strip()]

    def model_post_init(self, _ctx) -> None:
        if not (self.left_points or self.right_points):
            raise ValueError("needs points on at least one side")


class DominoChainParams(_Base):
    """Cause and effect: each link knocks over the next, ending in the final effect."""
    template: Literal["domino_chain"] = "domino_chain"
    title: str = Field(default="", max_length=80)
    links: list[str]
    effect: str = Field(default="", max_length=40)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("links")
    @classmethod
    def _links(cls, v):
        return _short_list(v, 2, 6, "links")


class StatRevealParams(_Base):
    """One big number from the sources: counter, ring (a percentage) or a 10 x 10 grid of dots."""
    template: Literal["stat_reveal"] = "stat_reveal"
    title: str = Field(default="", max_length=80)
    value: float = Field(ge=0, le=1e13)
    prefix: str = Field(default="", max_length=6)
    suffix: str = Field(default="", max_length=12)
    label: str = Field(default="", max_length=60)
    style: Literal["counter", "ring", "dots"] = "counter"
    duration_s: float = Field(default=6.0, ge=2, le=20)


class QuoteParams(_Base):
    """A quotation from the sources with its speaker; `highlight` is a word or phrase from the quote."""
    template: Literal["quote_card"] = "quote_card"
    title: str = Field(default="", max_length=80)
    quote: str = Field(min_length=3, max_length=160)
    author: str = Field(default="", max_length=40)
    highlight: str = Field(default="", max_length=30)
    duration_s: float = Field(default=7.0, ge=2, le=20)

    def model_post_init(self, _ctx) -> None:
        if self.highlight and self.highlight.lower() not in self.quote.lower():
            self.highlight = ""


class ProsConsParams(_Base):
    """Pros and cons on a balance scale that tips toward the verdict."""
    template: Literal["pros_cons"] = "pros_cons"
    title: str = Field(default="", max_length=80)
    pros: list[str]
    cons: list[str]
    verdict: Literal["pros", "cons", "even"] | None = None
    pros_label: str = Field(default="", max_length=20)
    cons_label: str = Field(default="", max_length=20)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("pros", "cons")
    @classmethod
    def _sides(cls, v):
        return _short_list(v, 1, 4, "points per side")


class RankingParams(_Base):
    """A ranking that races into order: by `values` (supported numbers only) or, without them, as given."""
    template: Literal["ranking"] = "ranking"
    title: str = Field(default="", max_length=80)
    items: list[str]
    values: list[float] = Field(default_factory=list, max_length=6)
    unit: str = Field(default="", max_length=12)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("items")
    @classmethod
    def _rank_items(cls, v):
        return _short_list(v, 2, 6, "items", 28)

    @field_validator("values")
    @classmethod
    def _vals(cls, v):
        return _numbers(v)

    def model_post_init(self, _ctx) -> None:
        if self.values and len(self.values) != len(self.items):
            raise ValueError("values need one number per item")


class FunnelParams(_Base):
    """Narrowing stages, widest first; optional values (supported numbers only), one per stage."""
    template: Literal["funnel"] = "funnel"
    title: str = Field(default="", max_length=80)
    stages: list[str]
    values: list[float] = Field(default_factory=list, max_length=5)
    unit: str = Field(default="", max_length=12)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("stages")
    @classmethod
    def _stages(cls, v):
        return _short_list(v, 2, 5, "stages", 32)

    @field_validator("values")
    @classmethod
    def _vals(cls, v):
        return _numbers(v)

    def model_post_init(self, _ctx) -> None:
        if self.values and len(self.values) != len(self.stages):
            raise ValueError("values need one number per stage")


class MythFact(BaseModel):
    myth: str = Field(min_length=1, max_length=80)
    fact: str = Field(min_length=1, max_length=80)


class MythFactParams(_Base):
    """1-3 myths, each struck out and flipped over to the fact."""
    template: Literal["myth_fact"] = "myth_fact"
    title: str = Field(default="", max_length=80)
    pairs: list[MythFact] = Field(min_length=1, max_length=3)
    duration_s: float = Field(default=8.0, ge=2, le=20)


class SpotlightParams(_Base):
    """A spotlight roams over 3-8 words and settles on `focus` (one of the words)."""
    template: Literal["spotlight"] = "spotlight"
    title: str = Field(default="", max_length=80)
    words: list[str]
    focus: str = Field(default="", max_length=24)
    caption: str = Field(default="", max_length=40)
    duration_s: float = Field(default=7.0, ge=2, le=20)

    @field_validator("words")
    @classmethod
    def _words(cls, v):
        return _short_list(v, 3, 8, "words", 24)

    def model_post_init(self, _ctx) -> None:
        if self.focus and self.focus.lower() not in (w.lower() for w in self.words):
            raise ValueError("focus must be one of the words")


class RoadmapParams(_Base):
    """A journey or plan: stops along a winding road (first stop first) toward an optional goal."""
    template: Literal["roadmap"] = "roadmap"
    title: str = Field(default="", max_length=80)
    stops: list[str]
    goal: str = Field(default="", max_length=30)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    @field_validator("stops")
    @classmethod
    def _stops(cls, v):
        return _short_list(v, 2, 6, "stops")


class DecisionOption(BaseModel):
    choice: str = Field(min_length=1, max_length=24)
    outcome: str = Field(default="", max_length=40)


class DecisionTreeParams(_Base):
    """A question branching into 2-3 choices and their outcomes; `picked` (0-based) lights one path."""
    template: Literal["decision_tree"] = "decision_tree"
    title: str = Field(default="", max_length=80)
    question: str = Field(min_length=1, max_length=60)
    options: list[DecisionOption] = Field(min_length=2, max_length=3)
    picked: int | None = Field(default=None, ge=0, le=2)
    duration_s: float = Field(default=8.0, ge=2, le=20)

    def model_post_init(self, _ctx) -> None:
        if self.picked is not None and self.picked >= len(self.options):
            raise ValueError("picked must point at one of the options")


class Carousel3DParams(_Scene3D):
    """3D: 3-6 items on cards around a turning ring, each brought to the front in turn."""
    template: Literal["carousel_3d"] = "carousel_3d"
    items: list[str]

    @field_validator("items")
    @classmethod
    def _cards(cls, v):
        return _short_list(v, 3, 6, "items", 32)


class Podium3DParams(_Scene3D):
    """3D: the top two or three (first place first) rise on a podium."""
    template: Literal["podium_3d"] = "podium_3d"
    places: list[str]

    @field_validator("places")
    @classmethod
    def _places(cls, v):
        return _short_list(v, 2, 3, "places", 24)


class CubeFaces3DParams(_Scene3D):
    """3D: 2-5 sides of one idea written on the faces of a turning cube (the fifth goes on top)."""
    template: Literal["cube_faces_3d"] = "cube_faces_3d"
    faces: list[str]

    @field_validator("faces")
    @classmethod
    def _faces(cls, v):
        return _short_list(v, 2, 5, "faces", 32)


class SpiralTimeline3DParams(_Scene3D):
    """3D: 2-6 events (earliest first) on a helix that climbs through space."""
    template: Literal["spiral_timeline_3d"] = "spiral_timeline_3d"
    events: list[str]

    @field_validator("events")
    @classmethod
    def _events(cls, v):
        return _short_list(v, 2, 6, "events", 24)


# templates whose fields are numbers the sources must contain, and the fields that hold them
NUMBER_FIELDS = {"simple_chart": ("values",), "pie_chart": ("values",), "bar_chart_3d": ("values",),
                 "stat_reveal": ("value",), "ranking": ("values",), "funnel": ("values",)}
# the general templates: any digits in their text must also come from the sources (years, counts, ...)
GENERAL = {"before_after", "domino_chain", "stat_reveal", "quote_card", "pros_cons", "ranking", "funnel", "myth_fact",
           "spotlight", "roadmap", "decision_tree", "carousel_3d", "podium_3d", "cube_faces_3d", "spiral_timeline_3d"}


TEMPLATES: dict[str, tuple[str, str, type[BaseModel]]] = {
    "before_after": ("before_after.py", "BeforeAfterScene", BeforeAfterParams),
    "domino_chain": ("domino_chain.py", "DominoChainScene", DominoChainParams),
    "stat_reveal": ("stat_reveal.py", "StatRevealScene", StatRevealParams),
    "quote_card": ("quote_card.py", "QuoteCardScene", QuoteParams),
    "pros_cons": ("pros_cons.py", "ProsConsScene", ProsConsParams),
    "ranking": ("ranking.py", "RankingScene", RankingParams),
    "funnel": ("funnel.py", "FunnelScene", FunnelParams),
    "myth_fact": ("myth_fact.py", "MythFactScene", MythFactParams),
    "spotlight": ("spotlight.py", "SpotlightScene", SpotlightParams),
    "roadmap": ("roadmap.py", "RoadmapScene", RoadmapParams),
    "decision_tree": ("decision_tree.py", "DecisionTreeScene", DecisionTreeParams),
    "carousel_3d": ("carousel_3d.py", "Carousel3DScene", Carousel3DParams),
    "podium_3d": ("podium_3d.py", "Podium3DScene", Podium3DParams),
    "cube_faces_3d": ("cube_faces_3d.py", "CubeFaces3DScene", CubeFaces3DParams),
    "spiral_timeline_3d": ("spiral_timeline_3d.py", "SpiralTimeline3DScene", SpiralTimeline3DParams),
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
    "orbit_3d": ("orbit_3d.py", "Orbit3DScene", Orbit3DParams),
    "surface_3d": ("surface_3d.py", "Surface3DScene", Surface3DParams),
    "bar_chart_3d": ("bar_chart_3d.py", "BarChart3DScene", BarChart3DParams),
    "dna_helix_3d": ("dna_helix_3d.py", "DNAHelix3DScene", DNAHelix3DParams),
    "molecule_3d": ("molecule_3d.py", "Molecule3DScene", Molecule3DParams),
    "globe_3d": ("globe_3d.py", "Globe3DScene", Globe3DParams),
    "vector_field_3d": ("vector_field_3d.py", "VectorField3DScene", VectorField3DParams),
    "crystal_lattice_3d": ("crystal_lattice_3d.py", "CrystalLattice3DScene", CrystalLattice3DParams),
    "neural_net_3d": ("neural_net_3d.py", "NeuralNet3DScene", NeuralNet3DParams),
    "layer_stack_3d": ("layer_stack_3d.py", "LayerStack3DScene", LayerStack3DParams),
    "planet_layers_3d": ("planet_layers_3d.py", "PlanetLayers3DScene", PlanetLayers3DParams),
    "wave_3d": ("wave_3d.py", "Wave3DScene", Wave3DParams),
    "solids_3d": ("solids_3d.py", "Solids3DScene", Solids3DParams),
    "galaxy_3d": ("galaxy_3d.py", "Galaxy3DScene", Galaxy3DParams),
}

THREE_D = {k for k in TEMPLATES if k.endswith("_3d")}


def remotion_fallback(t: dict) -> tuple[str, dict] | None:
    """A Remotion visual showing the same (already validated) data, for when a Manim clip cannot be made."""
    head = str(t.get("title", ""))
    if t.get("steps"):
        return "process", {"heading": head, "steps": t["steps"][:6]}
    events = [e if isinstance(e, dict) else {"label": str(e)} for e in t.get("events") or []]
    if len(events) >= 2:
        return "timeline", {"heading": head, "events": events[:6]}
    name = t.get("template")
    if name == "before_after" and t.get("left_points") and t.get("right_points"):
        return "comparison", {"heading": head, "leftTitle": t.get("left_title") or "Before",
                              "rightTitle": t.get("right_title") or "After",
                              "leftPoints": t["left_points"], "rightPoints": t["right_points"]}
    if name == "pros_cons":
        return "comparison", {"heading": head, "leftTitle": t.get("pros_label") or "Pros",
                              "rightTitle": t.get("cons_label") or "Cons",
                              "leftPoints": t.get("pros") or [], "rightPoints": t.get("cons") or []}
    if name == "stat_reveal":
        return "stat", {"value": t.get("value", 0), "prefix": t.get("prefix", ""), "suffix": t.get("suffix", ""),
                        "label": t.get("label") or head}
    if name == "roadmap" and len(t.get("stops") or []) >= 2:
        return "process", {"heading": head, "steps": t["stops"][:6]}
    points = (t.get("links") or t.get("items") or t.get("places") or t.get("faces") or t.get("words")
              or [x.get("fact", "") for x in t.get("pairs") or []]
              or [o.get("outcome") or o.get("choice", "") for o in t.get("options") or []])
    if points:
        return "key_points", {"heading": head, "points": [str(x)[:60] for x in points][:6]}
    return None

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

