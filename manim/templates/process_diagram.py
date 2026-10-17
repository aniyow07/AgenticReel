"""Vertical process diagram: steps pop in one by one, energy flows down the arrows,
and each step lights up as the flow reaches it."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arrow, Create, FadeIn, Flash, GrowArrow, Indicate, Line, RoundedRectangle, Scene,  # noqa: E402
                   VGroup, Write)

from _common import DOWN, UP, ambient, colors, fit_width, label, load_params, scene_seconds, stream  # noqa: E402


class ProcessDiagramScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        steps = [s for s in p.get("steps", []) if str(s).strip()][:6]
        if len(steps) < 2:
            raise ValueError("process_diagram needs at least two steps")
        total = scene_seconds(p, 6.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "process" + "".join(steps))

        title = fit_width(label(p.get("title", ""), 40, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        box_h = min(1.4, (fh - 2.4) / (len(steps) * 1.6))
        boxes = VGroup()
        for i, s in enumerate(steps):
            t = fit_width(label(s, 30, C["text"]), fw * 0.66)
            r = RoundedRectangle(corner_radius=0.18, width=fw * 0.8, height=box_h, stroke_color=C["primary"],
                                 stroke_width=4, fill_color=C["surface"], fill_opacity=1)
            num = label(str(i + 1), 26, C["accent"]).move_to(r.get_left() + [0.45, 0, 0])
            t.move_to(r)
            boxes.add(VGroup(r, t, num))
        boxes.arrange(DOWN, buff=max(0.55, box_h * 0.6))
        if boxes.height > fh - title.height - 1.0:
            boxes.scale_to_fit_height(fh - title.height - 1.0)
        boxes.move_to([0, (title.get_bottom()[1] - fh / 2) / 2, 0])

        arrows = [Arrow(boxes[i].get_bottom(), boxes[i + 1].get_top(), buff=0.06, color=C["accent"],
                        stroke_width=6, max_tip_length_to_length_ratio=0.35) for i in range(len(steps) - 1)]
        paths = [Line(boxes[i].get_bottom(), boxes[i + 1].get_top()) for i in range(len(steps) - 1)]

        build = (total - 0.6) * 0.6
        step_time = build / len(steps)
        self.play(Write(title), run_time=0.6)
        for i, b in enumerate(boxes):
            if i > 0:
                self.play(GrowArrow(arrows[i - 1]), run_time=step_time * 0.3)
                self.add(stream(paths[i - 1], C["accent"], count=2, speed=0.9))
            self.play(Create(b[0]), FadeIn(b[1], shift=UP * 0.15), FadeIn(b[2], scale=1.5),
                      run_time=step_time * 0.7)
        # Remaining time: the flow keeps moving and each step lights up in turn.
        rest = total - 0.6 - build
        each = max(0.3, rest / len(steps))
        for b in boxes:
            self.play(Indicate(b[0], color=C["accent"], scale_factor=1.06),
                      Flash(b[0].get_right(), color=C["accent"], line_length=0.25, num_lines=8, flash_radius=0.3),
                      run_time=each)
