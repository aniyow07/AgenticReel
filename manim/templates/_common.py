"""Shared helpers for AgentReel's trusted Manim templates.

Templates never receive code. They read a JSON parameter file whose path is
given in the AGENTREEL_MANIM_PARAMS environment variable (set by
rendering/manim_runner.py after Pydantic validation) and re-check the fields
they use. Only ordinary Text mobjects are used, so no LaTeX install is needed.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from pathlib import Path

from manim import DOWN, LEFT, RIGHT, UP, Circle, Dot, Text, VGroup, config

DEFAULT = {"background": "#0B1020", "surface": "#151C33", "primary": "#7C9CFF", "accent": "#FFB547",
           "text": "#F5F7FF", "mutedText": "#A9B2D0"}
# kept for backwards compatibility with older templates
BG, SURFACE, PRIMARY, ACCENT, TEXT, MUTED = (DEFAULT[k] for k in
                                             ("background", "surface", "primary", "accent", "text", "mutedText"))
FONT = "Segoe UI"
MAX_TEXT = 80
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def load_params() -> dict:
    path = os.environ.get("AGENTREEL_MANIM_PARAMS")
    if not path:
        raise RuntimeError("AGENTREEL_MANIM_PARAMS is not set")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manim params must be a JSON object")
    return data


def colors(p: dict) -> dict:
    """Palette from the params (validated hex colours only), falling back to the defaults."""
    pal = dict(DEFAULT)
    for k, v in (p.get("palette") or {}).items():
        if k in pal and isinstance(v, str) and _HEX.match(v):
            pal[k] = v
    return pal


def setup_frame() -> None:
    """Match the frame aspect to the requested pixel size."""
    config.background_color = DEFAULT["background"]
    config.frame_width = config.frame_height * config.pixel_width / config.pixel_height


# Applied at import time: Manim parses CLI flags before loading the template
# module but builds the camera only when the Scene is created.
setup_frame()


def clean(s: object) -> str:
    text = str(s).replace("\n", " ").strip()
    return text[:MAX_TEXT]


def label(s: str, size: float = 34, color: str = TEXT, weight: str = "BOLD") -> Text:
    return Text(clean(s), font=FONT, font_size=size, color=color, weight=weight)


def fit_width(mob, max_width: float):
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    return mob


def scene_seconds(params: dict, default: float) -> float:
    """Target clip length so the clip fits its storyboard scene."""
    try:
        v = float(params.get("duration_s", default))
    except (TypeError, ValueError):
        v = default
    return max(2.0, min(v, 20.0))


def ambient(scene, C: dict, seed: str) -> VGroup:
    """Slowly drifting, softly pulsing background shapes so the clip never sits still."""
    group = VGroup()
    if config.transparent:  # the video behind the clip already moves; keep the diagram clean
        return group
    rng = random.Random(seed)
    fw, fh = scene.camera.frame_width, scene.camera.frame_height
    for i in range(7):
        r = rng.uniform(0.6, 2.2)
        c = Circle(radius=r, stroke_width=0, fill_color=C["primary"] if i % 2 else C["accent"],
                   fill_opacity=rng.uniform(0.04, 0.08))
        c.move_to([rng.uniform(-fw / 2, fw / 2), rng.uniform(-fh / 2, fh / 2), 0])
        c.base = c.get_center().copy()
        c.phase, c.speed, c.amp = rng.uniform(0, 6.28), rng.uniform(0.25, 0.6), rng.uniform(0.3, 0.9)
        c.t = 0.0

        def drift(m, dt):
            m.t += dt
            m.move_to(m.base + [m.amp * math.sin(m.t * m.speed + m.phase),
                                m.amp * 0.7 * math.cos(m.t * m.speed * 1.3 + m.phase), 0])
        c.add_updater(drift)
        group.add(c)
    for i in range(18):
        d = Dot(radius=rng.uniform(0.02, 0.05), color=C["text"], fill_opacity=rng.uniform(0.15, 0.35))
        d.move_to([rng.uniform(-fw / 2, fw / 2), rng.uniform(-fh / 2, fh / 2), 0])
        d.vy = rng.uniform(0.1, 0.35)

        def rise(m, dt, fh=fh):
            m.shift(UP * m.vy * dt)
            if m.get_y() > fh / 2 + 0.2:
                m.set_y(-fh / 2 - 0.2)
        d.add_updater(rise)
        group.add(d)
    scene.add(group)
    return group


def stream(path_mob, color: str, count: int = 3, speed: float = 0.6, radius: float = 0.07) -> VGroup:
    """Dots that flow continuously along a path (e.g. along an arrow) to show movement."""
    dots = VGroup()
    for k in range(count):
        d = Dot(radius=radius, color=color)
        d.p = k / count

        def move(m, dt, path=path_mob):
            m.p = (m.p + speed * dt) % 1.0
            m.move_to(path.point_from_proportion(m.p))
            m.set_opacity(0.25 + 0.75 * math.sin(math.pi * m.p))
        d.add_updater(move)
        move(d, 0)
        dots.add(d)
    return dots


import ast  # noqa: E402

_FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp, "log": math.log, "ln": math.log,
          "sqrt": math.sqrt, "abs": abs}
_CONSTS = {"pi": math.pi, "e": math.e}
_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)


def compile_expr(text: str):
    """y = f(x) from a plain math expression ("x^2 - 3*x", "2*sin(x)"). Only numbers, x, + - * / ^ and a few
    named functions are allowed: the text is parsed, never executed as Python."""
    src = str(text).replace("^", "**").replace("−", "-").replace("×", "*")
    tree = ast.parse(src, mode="eval")

    def ev(n, x):
        if isinstance(n, ast.Expression):
            return ev(n.body, x)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)  # floats overflow cleanly; huge integer powers would hang
        if isinstance(n, ast.Name):
            if n.id == "x":
                return x
            if n.id in _CONSTS:
                return _CONSTS[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, _OPS):
            v = ev(n.operand, x)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and isinstance(n.op, _OPS):
            a, b = ev(n.left, x), ev(n.right, x)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                return a / b
            return a ** b
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and len(n.args) == 1:
            return _FUNCS[n.func.id](ev(n.args[0], x))
        raise ValueError(f"not allowed in a function: {ast.dump(n)[:40]}")

    try:
        ev(tree, 0.5)  # raises ValueError now for anything outside the allowed grammar
    except (ArithmeticError, OverflowError):
        pass  # a pole or domain error at 0.5 is fine; it is only a gap in the curve

    def f(x: float) -> float:
        try:
            y = ev(tree, x)
            return float(y) if isinstance(y, (int, float)) and math.isfinite(y) else float("nan")
        except (ArithmeticError, ValueError, OverflowError):
            return float("nan")
    return f


__all__ = [
    "BG", "SURFACE", "PRIMARY", "ACCENT", "TEXT", "MUTED", "FONT", "DEFAULT",
    "load_params", "setup_frame", "clean", "label", "fit_width", "scene_seconds", "colors", "ambient", "stream",
    "UP", "DOWN", "LEFT", "RIGHT", "VGroup",
]
