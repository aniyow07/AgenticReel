"""3D podium: the top two or three (first place first) rise from the floor on solid blocks, third and second
before first, each name floating above its block; confetti falls on the winner as the camera circles."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, RIGHT, Circle, Dot, FadeIn, GrowFromEdge, ManimColor, Prism, Text,  # noqa: E402
                   ThreeDScene, VGroup, interpolate_color)

from _common import FONT, clean, colors, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


class Podium3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:24] for x in p.get("places", []) if str(x).strip()][:3]
        if len(names) < 2:
            raise ValueError("podium_3d needs at least two places")
        n = len(names)
        self.set_camera_orientation(phi=68 * DEGREES, theta=-100 * DEGREES, zoom=min(0.85, fw / 7.6),
                                    frame_center=[0, 0, 1.4])  # aim above the floor so the names clear the title
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        hi, lo = ManimColor(C["accent"]), ManimColor(C["primary"])
        heights = [2.2, 1.5, 1.0]
        xs = [0, -1.75, 1.75]  # first in the middle, second on the left, third on the right
        W, D = 1.6, 1.6
        floor = Circle(radius=3.3, fill_color=C["primary"], fill_opacity=0.12, stroke_color=C["primary"],
                       stroke_width=2, stroke_opacity=0.5)
        blocks, tags, digits = [], [], []
        for r in range(n):
            col = interpolate_color(hi, lo, r / 2)
            b = Prism(dimensions=[W, D, heights[r]], fill_opacity=0.95, stroke_width=1, stroke_color=C["background"])
            b.set_fill(col).move_to([xs[r], 0, heights[r] / 2])
            blocks.append(b)
            num = Text(str(r + 1), font=FONT, font_size=64, color=C["background"], weight="BOLD")
            num.rotate(90 * DEGREES, axis=RIGHT).move_to([xs[r], -D / 2 - 0.01, heights[r] * 0.55])
            digits.append(num)
            t = Text(names[r], font=FONT, font_size=30, color=C["text"], weight="BOLD")
            if t.width > 1.9:
                t.scale_to_fit_width(1.9)
            t.move_to([xs[r], 0, heights[r] + 0.55])
            tags.append(t)
        self.add_fixed_orientation_mobjects(*tags)
        for t in tags:
            t.set_opacity(0)
        rng = random.Random("podium" + "".join(names))
        confetti = VGroup()
        for k in range(36):
            d = Dot(radius=0.05, color=rng.choice([C["accent"], C["primary"], C["text"], "#5BD6B0", "#E86FA8"]))
            d.home = [rng.uniform(-1.3, 1.3), rng.uniform(-1.0, 1.0), rng.uniform(3.0, 5.5)]
            d.move_to(d.home)
            d.v = rng.uniform(0.9, 1.6)
            d.sway = rng.uniform(-0.3, 0.3)

            def fall(m, dt):
                m.shift([m.sway * dt, 0, -m.v * dt])
                if m.get_z() < heights[0] + 0.05:
                    m.move_to(m.home)
            d.add_updater(fall)
            confetti.add(d)

        self.play(*show(title), FadeIn(floor), run_time=0.5)
        rise = max(0.35, (total - 3.0) / n)
        for r in reversed(range(n)):  # third, then second, then the winner
            self.play(GrowFromEdge(blocks[r], -OUT), run_time=rise * 0.6)
            self.play(FadeIn(digits[r]), tags[r].animate.set_opacity(1), run_time=rise * 0.4)
        self.add_fixed_orientation_mobjects(*confetti)
        self.add(confetti)
        self.begin_ambient_camera_rotation(rate=0.18)
        self.play(*show(*notes), tags[0].animate.scale(1.15), run_time=0.5)
        self.wait(max(0.1, total - self.renderer.time))
