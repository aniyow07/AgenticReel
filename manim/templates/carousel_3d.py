"""3D carousel: the items stand as cards on a ring that turns in space, bringing each card to the front in
turn, where it grows and lights up; names on cards facing away fade so they never show mirrored."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, RIGHT, Circle, FadeIn, ManimColor, RoundedRectangle, ThreeDScene,  # noqa: E402
                   ValueTracker, VGroup, interpolate_color, rate_functions)

from _common import clean, colors, label, load_params, look_of, overlay, scene_seconds, show, wrap  # noqa: E402


class Carousel3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:32] for x in p.get("items", []) if str(x).strip()][:6]
        if len(names) < 3:
            raise ValueError("carousel_3d needs at least three items")
        n = len(names)
        R = 2.4 if n <= 4 else 2.9
        cw, ch = min(2.4, 2 * R * math.sin(math.pi / n) * 0.9), 1.5
        self.set_camera_orientation(phi=74 * DEGREES, theta=-90 * DEGREES, zoom=min(0.95, fw / 7.5))
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        lo, hi = ManimColor(C["primary"]), ManimColor(C["accent"])

        cards = []
        for i, name in enumerate(names):
            col = interpolate_color(lo, hi, i / max(1, n - 1))
            box = RoundedRectangle(corner_radius=0.15, width=cw, height=ch, fill_color=col, fill_opacity=0.9,
                                   stroke_color=C["text"], stroke_width=2)
            t = label(wrap(name, 14, 2), 30, C["background"])
            if t.width > cw * 0.85:
                t.scale_to_fit_width(cw * 0.85)
            if t.height > ch * 0.7:
                t.scale_to_fit_height(ch * 0.7)
            t.shift(OUT * 0.01)  # just in front of the card face
            box.set_shade_in_3d(True)  # depth-sorted so front cards cover back ones; text draws last, front only
            c = VGroup(box, t)
            # stand the card up facing -y (towards the camera), push it out to the ring, then turn it into place
            c.rotate(90 * DEGREES, axis=RIGHT).shift([0, -R, ch / 2])
            c.rotate(i * 2 * math.pi / n, axis=OUT, about_point=[0, 0, 0])
            c.slot = i
            cards.append(c)
        floor = Circle(radius=R + 0.5, stroke_color=C["primary"], stroke_width=2, stroke_opacity=0.5,
                       fill_color=C["primary"], fill_opacity=0.08)
        ring = VGroup(*cards)
        spin = ValueTracker(0)
        ring.angle = 0.0

        def turn(m):
            d = spin.get_value() - m.angle
            if d:
                m.rotate(d, axis=OUT, about_point=[0, 0, 0])
                m.angle = spin.get_value()
            for c in m:
                a = c.slot * 2 * math.pi / n + m.angle  # 0 = straight in front of the camera
                front = math.cos(a)
                c[1].set_opacity(max(0.0, min(1.0, front * 2.2 - 0.6)))
                c[0].set_fill(opacity=0.35 + 0.55 * max(0.0, front))
        ring.add_updater(turn)
        turn(ring)

        self.play(*show(title), FadeIn(floor), FadeIn(ring, shift=OUT * 1.5), run_time=0.8)
        self.play(*show(*notes), run_time=0.3)
        step = max(0.5, (total - 1.6) / n)
        for k in range(1, n + 1):
            self.play(spin.animate.set_value(-k * 2 * math.pi / n), run_time=step * 0.7,
                      rate_func=rate_functions.ease_in_out_cubic)
            self.wait(step * 0.3)
        self.wait(max(0.1, total - self.renderer.time))
