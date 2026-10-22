"""3D globe: a wireframe planet spins while arcs launch between named hubs and packets race along them; the
camera tilts down from the equator to look over the network. Hub positions are decorative, not geographic."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, RIGHT, Circle, Create, Dot, GrowFromCenter, LaggedStart, ParametricFunction,  # noqa: E402
                   Sphere, ThreeDScene, VGroup)

from _common import SERIES, clean, colors, legend, load_params, look_of, overlay, scene_seconds, show, stream  # noqa: E402

R = 2.0


def _pt(lat, lon, r=R):
    return [r * math.cos(lat) * math.cos(lon), r * math.cos(lat) * math.sin(lon), r * math.sin(lat)]


class Globe3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:20] for x in p.get("hubs", []) if str(x).strip()][:6]
        if len(names) < 2:
            raise ValueError("globe_3d needs at least two hubs")
        self.set_camera_orientation(phi=88 * DEGREES, theta=-90 * DEGREES, zoom=min(0.9, fw / 8))
        title, *_ = overlay(self, p, C, look)
        cols = [C["accent"], C["primary"], *SERIES, C["text"]]
        key = legend(names, cols, C, fw, head=str(p.get("caption", ""))[:40])
        self.add_fixed_in_frame_mobjects(key)
        key.set_opacity(0)

        body = Sphere(radius=R * 0.985, resolution=(16, 24), fill_opacity=0.55, stroke_width=0)
        body.set_color(C["surface"])
        grid = VGroup()
        for lat in range(-60, 61, 30):
            c = Circle(radius=R * math.cos(math.radians(lat)), stroke_width=1.2, stroke_color=C["primary"],
                       stroke_opacity=0.45).shift(OUT * R * math.sin(math.radians(lat)))
            grid.add(c)
        for lon in range(0, 180, 30):
            m = Circle(radius=R, stroke_width=1.2, stroke_color=C["primary"], stroke_opacity=0.45)
            grid.add(m.rotate(90 * DEGREES, axis=RIGHT).rotate(lon * DEGREES, axis=OUT))

        rng = random.Random("globe" + "".join(names))
        n = len(names)
        spots = [(math.radians(rng.uniform(-45, 55)), 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)) for i in range(n)]
        hubs = VGroup(*[Dot(_pt(la, lo, R * 1.01), radius=0.11, color=cols[i % len(cols)])
                        for i, (la, lo) in enumerate(spots)])
        arcs = VGroup()
        pairs = [(i, (i + 1) % n) for i in range(n if n > 2 else 1)] + ([(0, n // 2)] if n > 3 else [])
        for a, b in pairs:
            pa, pb = _pt(*spots[a], r=1), _pt(*spots[b], r=1)
            om = math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(pa, pb))))) or 1e-3

            def f(t, pa=pa, pb=pb, om=om):
                s1, s2 = math.sin((1 - t) * om) / math.sin(om), math.sin(t * om) / math.sin(om)
                lift = R * (1 + 0.28 * math.sin(math.pi * t) * om / 2)
                return [lift * (s1 * x + s2 * y) for x, y in zip(pa, pb)]
            arcs.add(ParametricFunction(f, t_range=[0, 1], stroke_width=3, color=cols[a % len(cols)]))
        world = VGroup(body, grid, hubs, arcs)

        self.play(*show(title), Create(grid), GrowFromCenter(body), run_time=1.0)
        world.add_updater(lambda m, dt: m.rotate(0.25 * dt, axis=OUT, about_point=[0, 0, 0]))
        self.play(LaggedStart(*[GrowFromCenter(h) for h in hubs], lag_ratio=0.2), *show(key), run_time=0.7)
        self.move_camera(phi=58 * DEGREES, theta=-70 * DEGREES,
                         added_anims=[LaggedStart(*[Create(a) for a in arcs], lag_ratio=0.25)], run_time=1.4)
        packets = VGroup(*[stream(a, C["text"], count=2, speed=0.45 + 0.1 * (i % 3), radius=0.06)
                           for i, a in enumerate(arcs)])
        self.add(packets)
        self.wait(max(0.3, total - self.renderer.time))
