"""Donut chart: slices sweep in one after another with their share, the biggest slice pops out, and the
total sits in the middle."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (AnnularSector, FadeIn, Indicate, Scene, Text, VGroup, Write)  # noqa: E402

from _common import DOWN, LEFT, RIGHT, UP, ambient, clean, colors, fit_width, label, load_params, scene_seconds  # noqa: E402


class PieChartScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        labels = [clean(x)[:18] for x in p.get("labels", [])][:6]
        vals = [max(0.0, float(v)) for v in p.get("values", [])][:len(labels)]
        unit = clean(p.get("unit", ""))[:12]
        total_v = sum(vals) or 1
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "pie" + "".join(labels))
        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        R = min(fw * 0.36, fh * 0.2)
        center = [0, title.get_bottom()[1] - 0.6 - R, 0]
        palette = [C["accent"], C["primary"], "#5BD6B0", "#E86FA8", "#9B8CFF", C["mutedText"]]
        start = math.pi / 2
        slices, legend = [], VGroup()
        for i, v in enumerate(vals):
            ang = 2 * math.pi * v / total_v
            s = AnnularSector(inner_radius=R * 0.55, outer_radius=R, angle=-ang, start_angle=start,
                              fill_color=palette[i % len(palette)], fill_opacity=1, stroke_width=3,
                              stroke_color=C["background"]).shift(center)
            s.mid = start - ang / 2
            slices.append(s)
            start -= ang
            share = f"{100 * v / total_v:.0f}%"
            row = VGroup(AnnularSector(inner_radius=0, outer_radius=0.13, angle=2 * math.pi,
                                       fill_color=palette[i % len(palette)], fill_opacity=1, stroke_width=0),
                         Text(f"{labels[i]}  {share}", font="Segoe UI", font_size=24, color=C["text"]))
            row.arrange(RIGHT, buff=0.18)
            legend.add(row)
        legend.arrange(DOWN, aligned_edge=LEFT, buff=0.16).next_to([0, center[1] - R, 0], DOWN, buff=0.5)
        fit_width(legend, fw * 0.86)
        big = max(range(len(vals)), key=lambda i: vals[i])
        # shares of 100% say nothing in the middle; show the total for counts, the biggest slice for shares
        centre = (f"{total_v:,.0f}" + (f" {unit}" if unit else "")) if unit != "%" else \
            f"{labels[big]}\n{100 * vals[big] / total_v:.0f}%"
        mid_txt = Text(centre, font="Segoe UI", font_size=30, color=C["text"], weight="BOLD",
                       line_spacing=0.8).move_to(center)
        fit_width(mid_txt, R * 0.95)

        self.play(Write(title), run_time=0.6)
        sweep = max(1.0, (total - 2.0) * 0.6)
        for s, row in zip(slices, legend):
            self.play(FadeIn(s, scale=0.6), FadeIn(row, shift=LEFT * 0.2), run_time=sweep / len(slices))
        self.play(FadeIn(mid_txt, scale=1.3), run_time=0.4)
        out = [math.cos(slices[big].mid) * 0.25, math.sin(slices[big].mid) * 0.25, 0]
        self.play(slices[big].animate.shift(out), Indicate(legend[big], color=C["accent"]), run_time=0.6)
        self.wait(max(0.3, total - self.renderer.time))
