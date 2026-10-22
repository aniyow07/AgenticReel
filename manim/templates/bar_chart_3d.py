"""3D bar chart: solid bars rise from a floor grid one after another with their value on top, the tallest bar
flashes, and the camera swings slowly round the chart. Values must come from supported facts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, IN, OUT, PI, RIGHT, FadeIn, Indicate, NumberPlane, Prism, Text, ThreeDScene,  # noqa: E402
                   Transform)

from _common import clean, colors, heading, load_params, look_of, scene_seconds  # noqa: E402


def _fmt(v: float, unit: str) -> str:
    s = f"{v:,.0f}" if abs(v) >= 100 or v == int(v) else f"{v:,.1f}"
    return f"{s}{unit}" if unit in ("%", "x") else (f"{s} {unit}" if unit else s)


def _upright(text: Text) -> Text:
    """Stand flat text up so it faces the camera from the front of the chart."""
    return text.rotate(PI / 2, axis=RIGHT)


class BarChart3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        labels = [clean(x)[:14] for x in p.get("labels", [])][:8]
        vals = [max(0.0, float(v)) for v in p.get("values", [])][:len(labels)]
        if len(vals) < 2:
            raise ValueError("bar_chart_3d needs at least two values")
        unit = clean(p.get("unit", ""))[:12]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width

        title = heading(p.get("title", ""), C, fw, look)
        self.add_fixed_in_frame_mobjects(title)
        title.set_opacity(0)

        n = len(vals)
        gap = min(1.3, 7.0 / n)
        w = gap * 0.62
        top = max(vals) or 1
        H = 3.0
        z0 = -H / 2  # floor below the centre so the bars stand in the middle of the frame
        self.set_camera_orientation(phi=70 * DEGREES, theta=-72 * DEGREES, zoom=min(0.85, fw / (n * gap + 2.5)))
        floor = NumberPlane(x_range=[-n * gap / 2 - 0.6, n * gap / 2 + 0.6, gap / 2], y_range=[-1.2, 1.2, 0.6],
                            background_line_style={"stroke_color": C["mutedText"], "stroke_opacity": 0.35,
                                                   "stroke_width": 1}, axis_config={"stroke_opacity": 0}).shift([0, 0, z0])
        palette = [C["primary"], C["accent"]]
        bars, starts, tags, names = [], [], [], []
        for i, v in enumerate(vals):
            x = (i - (n - 1) / 2) * gap
            h = max(0.04, H * v / top)
            bar = Prism(dimensions=[w, w, h], fill_opacity=0.95, stroke_width=0.6, stroke_color=C["background"])
            bar.set_fill(palette[i % 2]).move_to([x, 0, z0 + h / 2])
            start = bar.copy().stretch(0.01, 2, about_edge=IN)
            tag = _upright(Text(_fmt(v, unit), font="Segoe UI", font_size=22, color=C["text"], weight="BOLD"))
            tag.move_to([x, 0, z0 + h + 0.3])
            name = _upright(Text(labels[i], font="Segoe UI", font_size=18, color=C["mutedText"]))
            if name.width > gap * 0.95:
                name.scale_to_fit_width(gap * 0.95)
            name.move_to([x, -w / 2 - 0.35, z0 + 0.02])
            bars.append(bar)
            starts.append(start)
            tags.append(tag)
            names.append(name)

        self.play(title.animate.set_opacity(1), FadeIn(floor), *[FadeIn(nm) for nm in names], run_time=0.8)
        self.begin_ambient_camera_rotation(rate=0.09)
        grow = max(1.2, (total - 2.5) * 0.55)
        for s, b, t in zip(starts, bars, tags):
            self.play(Transform(s, b), FadeIn(t, shift=OUT * 0.2), run_time=grow / n)
        big = max(range(n), key=lambda i: vals[i])
        self.play(Indicate(starts[big], color=C["accent"], scale_factor=1.06), run_time=0.6)
        self.wait(max(0.3, total - self.renderer.time))
