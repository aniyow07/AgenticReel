"""3D orbits: a nucleus (atom) or a star (planets) with bodies circling it on tilted rings while the camera
slowly turns around the whole system. Names sit in a fixed legend so they stay readable as the view moves."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, FadeIn, GrowFromCenter, Circle, Create, Dot, Dot3D, Sphere, Text, ThreeDScene,  # noqa: E402
                   VGroup, Write)

from _common import DOWN, LEFT, RIGHT, clean, colors, fit_width, heading, label, load_params, look_of, scene_seconds  # noqa: E402


class Orbit3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        kind = "planets" if p.get("kind") == "planets" else "atom"
        names = [clean(x)[:20] for x in p.get("orbiters", []) if str(x).strip()][:6]
        if not names:
            raise ValueError("orbit_3d needs at least one orbiter")
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        rng = random.Random("orbit" + "".join(names))
        self.set_camera_orientation(phi=68 * DEGREES, theta=-60 * DEGREES, zoom=1.0)

        title = heading(p.get("title", ""), C, fw, look)
        self.add_fixed_in_frame_mobjects(title)
        title.set_opacity(0)

        # the centre: a cluster of protons/neutrons, or one glowing star
        core = VGroup()
        if kind == "atom":
            for i in range(9):
                v = [rng.uniform(-1, 1) for _ in range(3)]
                n = math.sqrt(sum(c * c for c in v)) or 1
                r = 0.32 * rng.random() ** 0.5
                s = Sphere(radius=0.17, resolution=(8, 8)).move_to([c / n * r for c in v])
                s.set_color(C["accent"] if i % 2 else C["primary"])
                core.add(s)
        else:
            core.add(Sphere(radius=0.55, resolution=(14, 14)).set_color(C["accent"]))
        colors_ = [C["primary"], C["accent"], "#5BD6B0", "#E86FA8", "#9B8CFF", C["mutedText"]]
        reach = min(fw * 0.5, fh * 0.3)
        rings, bodies = VGroup(), VGroup()
        for i, _ in enumerate(names):
            if kind == "atom":
                R = reach * (0.75 + 0.08 * (i % 3))
                ring = Circle(radius=R, stroke_width=2, stroke_color=C["mutedText"], stroke_opacity=0.6)
                ring.rotate(i * math.pi / len(names), axis=[0, 0, 1]).rotate(55 * DEGREES + i * 20 * DEGREES,
                                                                              axis=[1, 0, 0])
                ring.rotate(i * 60 * DEGREES, axis=[0, 0, 1])
            else:
                R = reach * (0.3 + 0.7 * (i + 1) / len(names))
                ring = Circle(radius=R, stroke_width=2, stroke_color=C["mutedText"], stroke_opacity=0.5)
            body = Dot3D(radius=0.11 if kind == "atom" else 0.09 + 0.03 * (i % 3), color=colors_[i % len(colors_)])
            body.ring, body.a = ring, rng.uniform(0, 1)
            body.speed = (0.35 if kind == "atom" else 0.5 / (1 + i * 0.6)) * (1 if i % 2 == 0 or kind == "planets" else -1)
            body.move_to(ring.point_from_proportion(body.a))

            def orbit(m, dt):
                m.a = (m.a + m.speed * dt) % 1
                m.move_to(m.ring.point_from_proportion(m.a))
            body.add_updater(orbit)
            rings.add(ring)
            bodies.add(body)

        legend = VGroup()
        centre = clean(p.get("center", ""))[:24]
        if centre:
            legend.add(label(centre, 26, C["accent"]))
        for i, n in enumerate(names):
            legend.add(VGroup(Dot(radius=0.09, color=colors_[i % len(colors_)]),
                              Text(n, font="Segoe UI", font_size=22, color=C["text"])).arrange(RIGHT, buff=0.15))
        legend.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        fit_width(legend, fw * 0.8).to_edge(DOWN, buff=0.4).to_edge(LEFT, buff=fw * 0.08)
        self.add_fixed_in_frame_mobjects(legend)
        legend.set_opacity(0)

        self.play(title.animate.set_opacity(1), GrowFromCenter(core), run_time=0.8)
        self.begin_ambient_camera_rotation(rate=0.18)
        self.play(*[Create(r) for r in rings], run_time=1.0)
        self.add(bodies)
        self.play(FadeIn(bodies), legend.animate.set_opacity(1), run_time=0.6)
        self.wait(max(0.3, total - self.renderer.time))
