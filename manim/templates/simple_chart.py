"""Bar chart from supplied numbers only (the template never invents data).
Bars grow with live counters, then the largest value is highlighted."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (FadeIn, Flash, Indicate, Line, Rectangle, Scene, ValueTracker,  # noqa: E402
                   VGroup, Write, always_redraw)

from _common import DOWN, UP, ambient, colors, fit_width, label, load_params, scene_seconds  # noqa: E402


class SimpleChartScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        labels = [str(x) for x in p.get("labels", [])][:8]
        values = p.get("values", [])[:8]
        if not labels or len(labels) != len(values):
            raise ValueError("simple_chart needs equal-length labels and values")
        values = [float(v) for v in values]
        if any(math.isnan(v) or math.isinf(v) or v < 0 for v in values):
            raise ValueError("simple_chart values must be finite and non-negative")
        unit = str(p.get("unit", ""))[:12]
        total = scene_seconds(p, 6.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "chart" + "".join(labels))

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        n = len(values)
        chart_w = fw * 0.84
        chart_h = fh - title.height - 2.6
        base_y = -fh / 2 + 1.3
        left_x = -chart_w / 2
        slot = chart_w / n
        bar_w = slot * 0.62
        vmax = max(values) or 1.0
        decimals = 0 if all(float(v).is_integer() for v in values) else 1
        grow = ValueTracker(0.0)

        axis = Line([left_x, base_y, 0], [left_x + chart_w, base_y, 0], color=C["mutedText"], stroke_width=3)
        bars, counters, names = VGroup(), VGroup(), VGroup()
        for i, (lab, v) in enumerate(zip(labels, values)):
            cx = left_x + slot * (i + 0.5)
            color = C["primary"] if i % 2 == 0 else C["accent"]
            h_full = max(0.02, chart_h * v / vmax)

            def make_bar(cx=cx, h_full=h_full, color=color):
                h = max(0.01, h_full * grow.get_value())
                return Rectangle(width=bar_w, height=h, fill_color=color, fill_opacity=1, stroke_width=0) \
                    .move_to([cx, base_y + h / 2, 0])

            def make_counter(cx=cx, v=v, h_full=h_full):
                h = max(0.01, h_full * grow.get_value())
                # Text, not DecimalNumber: DecimalNumber needs a LaTeX install
                num = label(f"{v * grow.get_value():,.{decimals}f}{unit}", 30, C["text"])
                if num.width > slot * 0.95:
                    num.scale_to_fit_width(slot * 0.95)
                return num.move_to([cx, base_y + h + 0.3, 0])
            bars.add(always_redraw(make_bar))
            counters.add(always_redraw(make_counter))
            names.add(fit_width(label(lab, 20, C["mutedText"], weight="NORMAL"), slot * 0.95)
                      .next_to([cx, base_y, 0], DOWN, buff=0.15))

        grow_t = (total - 1.1) * 0.65
        self.play(Write(title), run_time=0.6)
        self.play(FadeIn(axis), *[FadeIn(nm, shift=UP * 0.2) for nm in names], run_time=0.5)
        self.add(bars, counters)
        self.play(grow.animate.set_value(1.0), run_time=grow_t)
        top = max(range(n), key=lambda i: values[i])
        rest = total - 1.1 - grow_t
        self.play(Indicate(bars[top], color=C["text"], scale_factor=1.05),
                  Flash([left_x + slot * (top + 0.5), base_y + chart_h + 0.3, 0], color=C["accent"],
                        flash_radius=0.4, line_length=0.3), run_time=max(0.3, rest * 0.6))
        self.wait(max(0.1, rest * 0.4))
