"""3D surface: axes draw in, a surface z = f(x, y) rises out of the flat floor and the camera circles it.
The surface is one of a fixed set of named shapes (no expressions), coloured from low to high."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import DEGREES, Create, Surface, ThreeDAxes, ThreeDScene, Transform  # noqa: E402

from _common import DOWN, clean, colors, fit_width, heading, label, load_params, look_of, scene_seconds  # noqa: E402

SHAPES = {
    "paraboloid": lambda x, y: 0.17 * (x * x + y * y) - 1.2,
    "saddle": lambda x, y: 0.25 * (x * x - y * y),
    "ripple": lambda x, y: 1.1 * math.cos(1.6 * math.hypot(x, y)) * math.exp(-0.18 * math.hypot(x, y)),
    "gaussian": lambda x, y: 2.0 * math.exp(-0.5 * (x * x + y * y)) - 0.6,
    "waves": lambda x, y: 0.8 * math.sin(1.2 * x) * math.cos(1.2 * y),
    "cone": lambda x, y: 1.6 - 0.75 * math.hypot(x, y),
}


class Surface3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        f = SHAPES.get(str(p.get("surface")), SHAPES["paraboloid"])
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        self.set_camera_orientation(phi=65 * DEGREES, theta=-50 * DEGREES, zoom=min(0.8, fw / 8.5))

        title = heading(p.get("title", ""), C, fw, look)
        cap = clean(p.get("caption", ""))[:40]
        fixed = [title]
        if cap:
            note = fit_width(label(cap, 26, C["accent"]), fw * 0.8).to_edge(DOWN, buff=0.5)
            fixed.append(note)
        for m in fixed:
            self.add_fixed_in_frame_mobjects(m)
            m.set_opacity(0)

        axes = ThreeDAxes(x_range=[-3, 3, 1], y_range=[-3, 3, 1], z_range=[-2, 2, 1], x_length=6, y_length=6,
                          z_length=4, axis_config={"color": C["mutedText"], "stroke_width": 2})

        def make(scale):
            s = Surface(lambda u, v: axes.c2p(u, v, scale * max(-2.0, min(2.0, f(u, v)))), u_range=[-3, 3],
                        v_range=[-3, 3], resolution=(22, 22), stroke_width=0.5, stroke_color=C["background"],
                        fill_opacity=0.9)
            s.set_fill_by_value(axes=axes, colorscale=[(C["primary"], -1.5), (C["accent"], 1.5)], axis=2)
            return s

        flat, surf = make(0.0), make(1.0)
        self.play(*[m.animate.set_opacity(1) for m in fixed[:1]], Create(axes), run_time=0.9)
        self.begin_ambient_camera_rotation(rate=0.2)
        self.play(Create(flat), run_time=0.6)
        self.play(Transform(flat, surf), *[m.animate.set_opacity(1) for m in fixed[1:]], run_time=1.6)
        self.wait(max(0.3, total - self.renderer.time))
