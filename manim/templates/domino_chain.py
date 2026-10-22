"""Cause and effect as a row of dominoes: each cause is a domino that tips into the next, its label popping up
as it falls, until the last one knocks over the final effect, which lands with a flash."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, DR, Create, Dot, FadeIn, Flash, Line, Rectangle, Rotate, Scene, VGroup, Write)  # noqa: E402

from _common import (DOWN, UP, ambient, card, clean, colors, heading, load_params, look_of,  # noqa: E402
                     mix, scene_seconds, wrap)


class DominoChainScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        links = [clean(x)[:40] for x in p.get("links") or [] if str(x).strip()][:6]
        if len(links) < 2:
            raise ValueError("domino_chain needs at least two links")
        effect = clean(p.get("effect", ""))[:40]
        ambient(self, C, "domino" + "".join(links))
        title = heading(p.get("title", ""), C, fw, look)
        n = len(links)
        floor_y = -fh / 2 + (1.9 if effect else 1.0)
        span = fw * 0.82
        h, w = 1.6, 0.3
        gap = min(1.6, (span - h) / max(1, n - 1))  # the last domino falls flat, so leave room for it
        x0 = -(gap * (n - 1) + h) / 2
        floor = Line([-fw / 2 + 0.3, floor_y, 0], [fw / 2 - 0.3, floor_y, 0], color=C["mutedText"], stroke_width=3)
        dominoes, tags = [], []
        top_room = title.get_bottom()[1] - 0.25
        for i, text in enumerate(links):
            x = x0 + i * gap
            col = mix(C["primary"], C["accent"], i / max(1, n - 1))
            body = Rectangle(width=w, height=h, fill_color=col, fill_opacity=1, stroke_color=C["text"],
                             stroke_width=1.5).move_to([x, floor_y + h / 2, 0])
            pips = VGroup(*[Dot(radius=0.035, color=C["background"]) for _ in range(min(i + 1, 6))])
            pips.arrange(DOWN, buff=0.12).move_to(body.get_center() + UP * h * 0.12)
            dominoes.append(VGroup(body, pips))
            # labels alternate between two heights so neighbours never overlap
            y = floor_y + h + 0.75 + (0 if i % 2 == 0 else 1.25)
            tag = card(wrap(text, 12, 3), C, min(2.2, gap * 2 - 0.4), look, col, size=20, min_h=0.6)
            tag.move_to([x, min(y, top_room - tag.height / 2), 0])
            stem = Line([x, floor_y + h + 0.1, 0], tag.get_bottom(), color=col, stroke_width=2, stroke_opacity=0.6)
            tags.append(VGroup(stem, tag))
        for t in tags:  # keep the outer labels inside the frame
            if t.get_left()[0] < -fw / 2 + 0.15:
                t.shift([-fw / 2 + 0.15 - t.get_left()[0], 0, 0])
            if t.get_right()[0] > fw / 2 - 0.15:
                t.shift([fw / 2 - 0.15 - t.get_right()[0], 0, 0])
        end = None
        if effect:
            end = card(effect, C, fw * 0.8, "pill" if look != "underline" else look, C["accent"], size=28)
            end.move_to([0, -fh / 2 + 0.75, 0])

        self.play(Write(title), Create(floor), run_time=0.6)
        self.play(*[FadeIn(d, shift=UP * 0.4) for d in dominoes], run_time=0.5)
        each = max(0.3, (total - 2.4) / n)
        # tipping about its bottom-right corner, a domino stops when its top meets the next one
        lean = 90 if gap - w >= h else math.degrees(math.asin((gap - w) / h))
        for i, d in enumerate(dominoes):
            pivot = d[0].get_corner(DR)
            angle = (90 if i == n - 1 else lean) * DEGREES
            self.play(Rotate(d, -angle, about_point=pivot), FadeIn(tags[i], shift=UP * 0.3), run_time=each * 0.7)
            if i < n - 1:
                self.play(Flash(dominoes[i + 1][0].get_top(), color=C["accent"], line_length=0.15, flash_radius=0.2,
                                num_lines=8), run_time=each * 0.3)
        if end:
            self.play(FadeIn(end, shift=UP * 0.6, scale=0.8), run_time=0.45)
            self.play(Flash(end, color=C["accent"], flash_radius=end.width / 2 + 0.15, num_lines=16), run_time=0.4)
        self.wait(max(0.1, total - self.renderer.time))
