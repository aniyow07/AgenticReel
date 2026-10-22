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
    return text[:MAX_TEXT].replace(LINE_BREAK, "\n")  # only wrap()'s line breaks survive


LINE_BREAK = " "


def label(s: str, size: float = 34, color: str = TEXT, weight: str = "BOLD") -> Text:
    text = clean(s)
    if "\n" in text:  # lines from wrap(): centred under each other (a multi-line Text is left-aligned)
        lines = [Text(t, font=FONT, font_size=size, color=color, weight=weight) for t in text.split("\n")]
        return VGroup(*lines).arrange(DOWN, buff=size / 100 * 0.18)
    return Text(text, font=FONT, font_size=size, color=color, weight=weight)


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


# ---------------- looks: so diagrams in different scenes and videos do not all share one design ----------------
LOOKS = ("rounded", "pill", "sharp", "glass", "underline")


def look_of(p: dict) -> str:
    """The look asked for in the params, else one picked from the scene's own text."""
    lk = p.get("look")
    if lk in LOOKS:
        return lk
    seed = str(p.get("title", "")) + str(p.get("template", ""))
    return LOOKS[sum(map(ord, seed)) % len(LOOKS)]


def card(text: str, C: dict, width: float, look: str, color: str | None = None, size: float = 26,
         min_h: float = 0.8):
    """A labelled box in one of the looks: rounded outline, filled pill, sharp card with an accent bar,
    frosted glass, or bare text with an underline."""
    from manim import Line, Rectangle, RoundedRectangle
    color = color or C["primary"]
    t = fit_width(label(text, size, C["text"]), width * 0.86)
    h = max(min_h, t.height + 0.42)
    if look == "pill":
        r = RoundedRectangle(corner_radius=h / 2, width=width, height=h, stroke_width=0, fill_color=color,
                             fill_opacity=0.32)
    elif look == "sharp":
        r = Rectangle(width=width, height=h, stroke_width=0, fill_color=C["surface"], fill_opacity=1)
        bar = Rectangle(width=0.12, height=h, stroke_width=0, fill_color=color, fill_opacity=1)
        bar.align_to(r, LEFT)
        r = VGroup(r, bar)
    elif look == "glass":
        r = RoundedRectangle(corner_radius=0.1, width=width, height=h, stroke_color=C["text"], stroke_width=1.5,
                             stroke_opacity=0.45, fill_color=C["text"], fill_opacity=0.07)
    elif look == "underline":
        r = Line(LEFT * width * 0.42, RIGHT * width * 0.42, color=color, stroke_width=5).shift(DOWN * (t.height / 2 + 0.14))
        box = VGroup(r, t)
        t.move_to([0, 0, 0])
        return box
    else:  # rounded
        r = RoundedRectangle(corner_radius=0.18, width=width, height=h, stroke_color=color, stroke_width=4,
                             fill_color=C["surface"], fill_opacity=1)
    t.move_to(r)
    return VGroup(r, t)


def heading(text: str, C: dict, fw: float, look: str):
    """The scene title, styled to match the look: centred, left-aligned with a bar, or with an underline."""
    from manim import Line, Rectangle
    t = fit_width(label(text, 38 if look != "glass" else 34, C["text"]), fw * 0.86)
    if look in ("sharp", "underline"):
        bar = Rectangle(width=0.14, height=t.height, stroke_width=0, fill_color=C["accent"], fill_opacity=1)
        g = VGroup(bar, t).arrange(RIGHT, buff=0.22)
        fit_width(g, fw * 0.88)
        g.to_edge(UP, buff=0.45).to_edge(LEFT, buff=fw * 0.06)
        return g
    t.to_edge(UP, buff=0.4)
    if look == "pill":
        u = Line(LEFT * 0.6, RIGHT * 0.6, color=C["accent"], stroke_width=6).next_to(t, DOWN, buff=0.14)
        return VGroup(t, u)
    return t


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
    "LOOKS", "look_of", "card", "heading", "compile_expr",
    "UP", "DOWN", "LEFT", "RIGHT", "VGroup",
]


def overlay(scene, p: dict, C: dict, look: str, notes=()) -> list:
    """Title at the top and up to three short notes at the bottom, pinned to the screen so they stay readable
    while the 3D camera moves. Hidden at first: fade them in with m.animate.set_opacity(1)."""
    fw = scene.camera.frame_width
    items = [heading(p.get("title", ""), C, fw, look)]
    texts = [clean(n)[:40] for n in notes if clean(n)][:3]
    if texts:
        g = VGroup(*[label(t, 24, C["accent"] if i == 0 else C["text"]) for i, t in enumerate(texts)])
        fit_width(g.arrange(DOWN, buff=0.12), fw * 0.84).to_edge(DOWN, buff=0.45)
        items.append(g)
    for m in items:
        scene.add_fixed_in_frame_mobjects(m)
        m.set_opacity(0)
    return items


def legend(names: list[str], cols: list[str], C: dict, fw: float, head: str = ""):
    """A fixed key of coloured dots and names for things that move around in 3D."""
    g = VGroup()
    if head:
        g.add(label(head, 24, C["accent"]))
    for i, n in enumerate(names):
        g.add(VGroup(Dot(radius=0.09, color=cols[i % len(cols)]),
                     Text(clean(n)[:24], font=FONT, font_size=22, color=C["text"])).arrange(RIGHT, buff=0.15))
    g.arrange(DOWN, aligned_edge=LEFT, buff=0.12)
    return fit_width(g, fw * 0.8).to_edge(DOWN, buff=0.4).to_edge(LEFT, buff=fw * 0.08)


def show(*mobs):
    """Animations that fade in overlay items hidden by overlay()/legend."""
    return [m.animate.set_opacity(1) for m in mobs]


SERIES = ("#5BD6B0", "#E86FA8", "#9B8CFF")


def mix(a: str, b: str, t: float) -> str:
    """A hex colour part way (t = 0..1) from a to b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def wrap(text: str, chars: int, max_lines: int = 3) -> str:
    """Break text into lines of about `chars` characters on word boundaries (Text has no wrapping)."""
    lines: list[str] = []
    for w in clean(text).split():  # split() also drops line breaks already in the text  # split() also drops any line break already in the text
        if lines and len(lines[-1]) + 1 + len(w) <= chars:
            lines[-1] += " " + w
        else:
            lines.append(w)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return LINE_BREAK.join(lines)


def num_text(v: float, like: object = None) -> str:
    """A number for display with thousands separators, keeping as many decimals as the source value had."""
    src = str(like if like is not None else v)
    dec = len(src.split(".")[1].rstrip("0")) if "." in src else 0
    return f"{v:,.{min(dec, 2)}f}"


GOOD, BAD = "#5BD6B0", "#FF6B7A"
