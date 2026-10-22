"""3D galaxy: hundreds of stars wind into a turning spiral seen face-on, then the camera swoops down to view
it edge-on and rises again at an angle. The number of arms is a small whole number, nothing else is supplied."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import DEGREES, OUT, Dot, FadeIn, ManimColor, ThreeDScene, VGroup, interpolate_color  # noqa: E402

from _common import colors, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


class Galaxy3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        try:
            arms = max(2, min(4, int(p.get("arms", 2))))
        except (TypeError, ValueError):
            arms = 2
        z0 = min(1.0, fw / 8)
        self.set_camera_orientation(phi=4 * DEGREES, theta=-90 * DEGREES, zoom=z0)
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        rng = random.Random(f"galaxy{arms}")
        warm, cool, white = ManimColor(C["accent"]), ManimColor(C["primary"]), ManimColor(C["text"])

        stars = VGroup()
        for i in range(380):
            t = rng.random() ** 0.8
            r = 0.25 + 3.2 * t
            ang = (i % arms) * 2 * math.pi / arms + 3.4 * t + rng.gauss(0, 0.28 * (1 - 0.4 * t))
            z = rng.gauss(0, 0.16 * (1 - t))
            col = interpolate_color(warm, cool, min(1, t * 1.3)) if rng.random() > 0.15 else white
            stars.add(Dot([r * math.cos(ang), r * math.sin(ang), z], radius=rng.uniform(0.018, 0.05), color=col,
                          fill_opacity=rng.uniform(0.5, 1)))
        for _ in range(70):  # the bright bulge in the middle
            r = abs(rng.gauss(0, 0.35))
            ang = rng.uniform(0, 2 * math.pi)
            stars.add(Dot([r * math.cos(ang), r * math.sin(ang), rng.gauss(0, 0.18)], radius=rng.uniform(0.03, 0.06),
                          color=interpolate_color(warm, white, rng.random())))
        glow = VGroup(*[Dot([0, 0, 0], radius=0.25 * k, color=C["accent"], fill_opacity=0.1) for k in (1, 2, 3)])
        self.add_fixed_orientation_mobjects(*stars, *glow)
        galaxy = VGroup(glow, stars)

        self.play(*show(title), FadeIn(glow), FadeIn(stars, lag_ratio=0.002), run_time=1.2)
        stars.add_updater(lambda m, dt: m.rotate(-0.35 * dt, axis=OUT, about_point=[0, 0, 0]))
        rest = max(1.5, total - self.renderer.time - 0.2)
        self.move_camera(phi=84 * DEGREES, theta=-40 * DEGREES, zoom=z0 * 1.1, added_anims=show(*notes),
                         run_time=rest * 0.5)
        self.move_camera(phi=58 * DEGREES, theta=-10 * DEGREES, zoom=z0 * 1.3, run_time=rest * 0.5)
        self.wait(max(0.1, total - self.renderer.time))
        galaxy.clear_updaters()
