"""Process diagram: steps pop in one by one, energy flows along the connectors, and each step lights up as
the flow reaches it. The look (card shape, title style) and layout (straight column or zigzag) vary per scene."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arrow, Create, FadeIn, Flash, GrowArrow, Indicate, Line, Scene, VGroup, Write)  # noqa: E402

from _common import (DOWN, LEFT, RIGHT, UP, ambient, card, colors, heading, label, load_params,  # noqa: E402
                     look_of, scene_seconds, stream)


class ProcessDiagramScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        steps = [s for s in p.get("steps", []) if str(s).strip()][:6]
        if len(steps) < 2:
            raise ValueError("process_diagram needs at least two steps")
        total = scene_seconds(p, 6.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "process" + "".join(steps))
        zigzag = look in ("pill", "glass", "underline")

        title = heading(p.get("title", ""), C, fw, look)
        w = fw * (0.62 if zigzag else 0.72)
        boxes = VGroup()
        for i, s in enumerate(steps):
            b = card(s, C, w, look, C["primary"] if i % 2 == 0 or look != "pill" else C["accent"], size=28)
            num = label(str(i + 1), 26, C["accent"]).next_to(b, LEFT, buff=0.2)  # outside, never over the text
            boxes.add(VGroup(*b, num))
        boxes.arrange(DOWN, buff=0.55)
        if zigzag:
            for i, b in enumerate(boxes):
                b.shift(RIGHT * (fw * 0.1 if i % 2 else -fw * 0.06))
        if boxes.height > fh - title.height - 1.2:
            boxes.scale_to_fit_height(fh - title.height - 1.2)
        boxes.move_to([0, (title.get_bottom()[1] - fh / 2) / 2, 0])

        def link(a, b):
            return Arrow(a.get_bottom(), b.get_top(), buff=0.06, color=C["accent"], stroke_width=6,
                         max_tip_length_to_length_ratio=0.35)
        arrows = [link(boxes[i], boxes[i + 1]) for i in range(len(steps) - 1)]
        paths = [Line(boxes[i].get_bottom(), boxes[i + 1].get_top()) for i in range(len(steps) - 1)]

        build = (total - 0.6) * 0.6
        step_time = build / len(steps)
        self.play(Write(title), run_time=0.6)
        for i, b in enumerate(boxes):
            if i > 0:
                self.play(GrowArrow(arrows[i - 1]), run_time=step_time * 0.3)
                self.add(stream(paths[i - 1], C["accent"], count=2, speed=0.9))
            self.play(Create(b[0]), *[FadeIn(m, shift=UP * 0.15) for m in b[1:]], run_time=step_time * 0.7)
        rest = total - 0.6 - build
        each = max(0.3, rest / len(steps))
        for b in boxes:
            self.play(Indicate(b[0], color=C["accent"], scale_factor=1.06),
                      Flash(b[0].get_right(), color=C["accent"], line_length=0.25, num_lines=8, flash_radius=0.3),
                      run_time=each)
