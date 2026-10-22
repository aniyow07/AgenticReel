"""3D waves: a named kind of wave travels along an axis. The camera starts side-on, where it looks like a flat
textbook drawing, then swings round to an angle to show the wave's depth (for light, the magnetic part)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, RIGHT, Circle, Create, FadeIn, Line, ParametricFunction, ThreeDScene, ValueTracker,  # noqa: E402
                   VGroup, always_redraw)

from _common import colors, legend, load_params, look_of, overlay, scene_seconds, show  # noqa: E402

KINDS = ("electromagnetic", "transverse", "standing", "longitudinal")
X0, X1, A, K, W = -3.6, 3.6, 1.0, 1.6, 3.2


class Wave3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        kind = p.get("kind") if p.get("kind") in KINDS else "transverse"
        self.set_camera_orientation(phi=90 * DEGREES, theta=-90 * DEGREES, zoom=min(1.0, fw / 8.2))
        title, *notes = overlay(self, p, C, look, [] if kind == "electromagnetic" else [p.get("caption", "")])
        key = None
        if kind == "electromagnetic":
            key = legend(["Electric field", "Magnetic field"], [C["accent"], C["primary"]], C, fw,
                         head=str(p.get("caption", ""))[:40])
            self.add_fixed_in_frame_mobjects(key)
            key.set_opacity(0)

        t = ValueTracker(0.0)
        axis = Line([X0 - 0.3, 0, 0], [X1 + 0.3, 0, 0], stroke_width=2, stroke_color=C["mutedText"])

        def h(x):
            if kind == "standing":
                return A * math.sin(K * (x - X0)) * math.cos(W * t.get_value())
            return A * math.sin(K * x - W * t.get_value())

        def curve(plane, col):  # plane "z": up/down (xz plane); "y": sideways (xy plane)
            def f(x):
                v = h(x)
                return [x, v, 0] if plane == "y" else [x, 0, v]

            def sticks():
                g = VGroup()
                for i in range(25):
                    x = X0 + (X1 - X0) * i / 24
                    g.add(Line([x, 0, 0], f(x), stroke_width=2, stroke_color=col, stroke_opacity=0.55))
                return g
            return (always_redraw(lambda: ParametricFunction(f, t_range=[X0, X1], stroke_width=5, color=col)),
                    always_redraw(sticks))

        def rings():
            g = VGroup()
            for i in range(19):
                x0 = X0 + (X1 - X0) * i / 18
                x = x0 + 0.35 * math.sin(K * x0 - W * t.get_value())
                squeeze = math.cos(K * x0 - W * t.get_value())  # > 0 where the rings bunch up
                c = Circle(radius=0.8, stroke_width=4, stroke_color=C["accent"] if squeeze > 0.3 else C["primary"],
                           stroke_opacity=0.5 + 0.5 * max(0.0, squeeze))
                g.add(c.rotate(90 * DEGREES, axis=[0, 1, 0]).move_to([x, 0, 0]))
            return g

        parts = []
        if kind == "longitudinal":
            parts.append(always_redraw(rings))
        else:
            parts += curve("z", C["accent"])
            if kind == "electromagnetic":
                parts += curve("y", C["primary"])

        clock = lambda m, dt: m.increment_value(dt)  # noqa: E731
        self.add(t)
        self.play(*show(title), Create(axis), run_time=0.5)
        self.play(*[FadeIn(x) for x in parts], *show(*notes), *([] if key is None else show(key)), run_time=0.6)
        t.add_updater(clock)
        self.wait(min(1.2, max(0.3, total * 0.15)))
        swing = max(1.0, (total - self.renderer.time) * 0.55)
        self.move_camera(phi=62 * DEGREES, theta=-35 * DEGREES, run_time=swing)
        self.begin_ambient_camera_rotation(rate=0.1)
        self.wait(max(0.1, total - self.renderer.time))
