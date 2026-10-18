"""Line chart: one to three series grow from left to right over labelled points; the last value of each
series pops with its number, and a legend names the series."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Axes, Create, Dot, FadeIn, Flash, Line, Scene, Text, VGroup, Write)  # noqa: E402

from _common import DOWN, LEFT, RIGHT, UP, ambient, clean, colors, fit_width, label, load_params, scene_seconds  # noqa: E402


def fmt(v: float, unit: str) -> str:
    s = f"{v:,.0f}" if abs(v) >= 100 else f"{v:g}"
    return f"{s}{unit}" if unit in ("%",) else (f"{s} {unit}" if unit else s)


class LineChartScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        labels = [clean(x)[:10] for x in p.get("labels", [])][:10]
        series = [s for s in p.get("series", []) if s.get("values")][:3]
        unit = clean(p.get("unit", ""))[:12]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "line" + "".join(labels))
        allv = [float(v) for s in series for v in s["values"]]
        lo, hi = min(0.0, min(allv)), max(allv) * 1.15 or 1
        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        n = len(labels)
        axes = Axes(x_range=[0, n - 1, 1], y_range=[lo, hi, (hi - lo) / 4], x_length=fw * 0.8,
                    y_length=min(fh * 0.45, fw), tips=False,
                    axis_config={"color": C["mutedText"], "stroke_width": 3})
        axes.next_to(title, DOWN, buff=0.7)
        ticks = VGroup(*[Text(l, font="Segoe UI", font_size=20, color=C["mutedText"]).next_to(axes.c2p(i, lo), DOWN, buff=0.15)
                         for i, l in enumerate(labels)])
        palette = [C["accent"], C["primary"], C["text"]]
        self.play(Write(title), Create(axes), FadeIn(ticks), run_time=1.0)

        legend = VGroup()
        grow = max(1.0, (total - 2.2) * 0.75)
        for k, s in enumerate(series):
            vals = [float(v) for v in s["values"]][:n]
            pts = [axes.c2p(i, v) for i, v in enumerate(vals)]
            segs = [Line(pts[i], pts[i + 1], color=palette[k], stroke_width=6) for i in range(len(pts) - 1)]
            dots = [Dot(pt, radius=0.08, color=palette[k]) for pt in pts]
            step = grow / len(series) / max(1, len(segs))
            self.play(FadeIn(dots[0], scale=1.5), run_time=step * 0.4)
            for seg, d in zip(segs, dots[1:]):
                self.play(Create(seg), FadeIn(d, scale=1.5), run_time=step)
            end = Text(fmt(vals[-1], unit), font="Segoe UI", font_size=24, color=palette[k], weight="BOLD")
            end.next_to(dots[-1], UP + LEFT * 0.3, buff=0.12)
            self.play(FadeIn(end, shift=UP * 0.1), Flash(dots[-1], color=palette[k], num_lines=8), run_time=0.4)
            if s.get("name"):
                legend.add(VGroup(Line(LEFT * 0.25, RIGHT * 0.25, color=palette[k], stroke_width=6),
                                  Text(clean(s["name"])[:20], font="Segoe UI", font_size=22, color=C["text"])).arrange(RIGHT, buff=0.15))
        if len(legend):
            legend.arrange(RIGHT, buff=0.5).next_to(ticks, DOWN, buff=0.4)
            fit_width(legend, fw * 0.9)
            self.play(FadeIn(legend, shift=UP * 0.1), run_time=0.4)
        self.wait(max(0.3, total - self.renderer.time))
