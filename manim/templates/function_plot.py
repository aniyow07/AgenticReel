"""Function graph: axes draw in, each curve traces itself, and a dot rides along the first curve with its
coordinates. Optional marked x values get a dashed guide and a labelled point (a root, a maximum ...)."""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Axes, Create, DashedLine, Dot, FadeIn, Flash, MoveAlongPath, Scene, Text, ValueTracker,  # noqa: E402
                   VGroup, Write, always_redraw)

from _common import DOWN, LEFT, RIGHT, UP, ambient, colors, compile_expr, fit_width, label, load_params, scene_seconds  # noqa: E402


SUPERS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def pretty(s: str) -> str:
    """x^2 -> x², ** -> ², * -> ·"""
    s = re.sub(r"(\^|\*\*)\(?(-?\d{1,2})\)?", lambda m: m.group(2).translate(SUPERS), str(s))
    return s.replace("*", "·").replace("sqrt", "√")


def nice_step(span: float) -> float:
    raw = span / 5
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    return min((m * mag for m in (1, 2, 5, 10) if m * mag >= raw), default=mag)


class FunctionPlotScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        funcs = [f for f in p.get("functions", []) if str(f.get("expr", "")).strip()][:3]
        x0, x1 = float(p.get("x_min", -5)), float(p.get("x_max", 5))
        fs = [compile_expr(f["expr"]) for f in funcs]
        xs = [x0 + (x1 - x0) * i / 200 for i in range(201)]
        ys = [y for f in fs for y in (f(x) for x in xs) if not math.isnan(y)]
        lo = float(p["y_min"]) if p.get("y_min") is not None else (min(ys) if ys else -5)
        hi = float(p["y_max"]) if p.get("y_max") is not None else (max(ys) if ys else 5)
        if hi - lo < 1e-6:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.1
        lo, hi = lo - pad, hi + pad
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "plot" + "".join(f["expr"] for f in funcs))

        title = fit_width(label(pretty(p.get("title", "")), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        axes = Axes(x_range=[x0, x1, nice_step(x1 - x0)], y_range=[lo, hi, nice_step(hi - lo)],
                    x_length=fw * 0.84, y_length=min(fh * 0.5, fw * 0.84 * 1.2), tips=False,
                    axis_config={"color": C["mutedText"], "stroke_width": 3, "include_numbers": False})
        axes.next_to(title, DOWN, buff=0.6)
        palette = [C["accent"], C["primary"], C["text"]]
        curves, legends = [], VGroup()
        for k, (f, spec) in enumerate(zip(fs, funcs)):
            g = axes.plot(lambda x, f=f: f(x), x_range=[x0, x1, (x1 - x0) / 200], color=palette[k],
                          stroke_width=6, discontinuities=None, use_smoothing=True)
            curves.append(g)
            name = pretty(spec.get("label") or ("y = " + spec["expr"]))
            legends.add(Text(name[:30], font="Cambria Math", font_size=26, color=palette[k]))
        legends.arrange(DOWN, aligned_edge=LEFT, buff=0.12).next_to(axes, DOWN, buff=0.35)
        fit_width(legends, fw * 0.86)

        self.play(Write(title), Create(axes), run_time=1.0)
        draw = max(0.8, (total - 2.6) * 0.55)
        for g, lg in zip(curves, legends):
            self.play(Create(g), FadeIn(lg, shift=UP * 0.1), run_time=draw / len(curves))

        marks = [float(m) for m in (p.get("mark_x") or [])][:3]
        for m in marks:
            y = fs[0](m)
            if math.isnan(y) or not (x0 <= m <= x1):
                continue
            pt = axes.c2p(m, y)
            guide = DashedLine(axes.c2p(m, lo), pt, color=C["mutedText"], stroke_width=2)
            dot = Dot(pt, radius=0.1, color=C["accent"])
            tag = Text(f"({m:g}, {y:.3g})", font="Cambria Math", font_size=24, color=C["text"]).next_to(dot, UP + RIGHT, buff=0.1)
            self.play(Create(guide), FadeIn(dot, scale=1.6), FadeIn(tag), Flash(dot, color=C["accent"]), run_time=0.6)

        # a dot that rides the first curve and reads out its coordinates
        t = ValueTracker(x0)
        f0 = fs[0]
        rider = always_redraw(lambda: Dot(axes.c2p(t.get_value(), f0(t.get_value()) if not math.isnan(f0(t.get_value())) else lo),
                                          radius=0.09, color=C["text"]))
        read = always_redraw(lambda: Text(
            f"x = {t.get_value():.1f}" + ("" if math.isnan(f0(t.get_value())) else f"   y = {f0(t.get_value()):.2f}"),
            font="Cambria Math", font_size=24, color=C["mutedText"]).next_to(axes, UP, buff=0.12).align_to(axes, RIGHT))
        self.add(rider, read)
        rest = max(0.8, total - 1.0 - draw - 0.6 * len(marks))
        self.play(t.animate.set_value(x1), run_time=rest)
