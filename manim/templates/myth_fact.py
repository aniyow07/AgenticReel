"""Myth versus fact: each myth appears on a card tagged MYTH, a stamp-like cross slams onto it, then the card
flips over to show the fact tagged FACT with a tick. Up to three pairs stack down the screen."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, Create, FadeIn, Flash, Line, RoundedRectangle, Scene, VGroup, VMobject, Write)  # noqa: E402

from _common import (BAD, DOWN, GOOD, LEFT, RIGHT, UP, ambient, clean, colors, fit_width, heading, label,  # noqa: E402
                     load_params, look_of, scene_seconds, wrap)


def side(text: str, tag: str, col: str, C: dict, w: float, h: float, look: str) -> VGroup:
    box = RoundedRectangle(corner_radius=0.06 if look == "sharp" else 0.22, width=w, height=h,
                           stroke_color=col, stroke_width=3 if look != "pill" else 0, fill_color=col,
                           fill_opacity=0.14 if look != "pill" else 0.28)
    chip = VGroup(RoundedRectangle(corner_radius=0.14, width=1.25, height=0.36, stroke_width=0, fill_color=col,
                                   fill_opacity=1), label(tag, 18, C["background"]))
    chip[1].move_to(chip[0])
    chip.move_to(box.get_corner(UP + LEFT) + [0.8, 0, 0])
    body = fit_width(label(wrap(text, 26, 2), 24, C["text"]), w - h - 0.5)  # room on the right for the mark
    if body.height > h * 0.62:
        body.scale_to_fit_height(h * 0.62)
    body.move_to(box.get_center() + DOWN * 0.08).align_to(box.get_left() + RIGHT * 0.35, LEFT)
    return VGroup(box, chip, body)


class MythFactScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        pairs = [(clean(x.get("myth", ""))[:80], clean(x.get("fact", ""))[:80]) for x in p.get("pairs") or []
                 if isinstance(x, dict) and str(x.get("myth", "")).strip() and str(x.get("fact", "")).strip()][:3]
        if not pairs:
            raise ValueError("myth_fact needs at least one myth and fact")
        ambient(self, C, "myth" + pairs[0][0])
        title = heading(p.get("title", ""), C, fw, look)
        top = title.get_bottom()[1] - 0.45
        slot = (top - (-fh / 2 + 0.35)) / len(pairs)
        h = min(2.1, slot - 0.3)
        w = fw * 0.86
        self.play(Write(title), run_time=0.5)
        each = max(1.2, (total - 0.8) / len(pairs))
        for k, (myth, fact) in enumerate(pairs):
            y = top - slot * (k + 0.5)
            front = side(myth, "MYTH", BAD, C, w, h, look).move_to([0, y, 0])
            back = side(fact, "FACT", GOOD, C, w, h, look).move_to([0, y, 0])
            cross = VGroup(Line(UP + LEFT, DOWN + RIGHT), Line(UP + RIGHT, DOWN + LEFT)).set_stroke(BAD, 10)
            cross.scale_to_fit_height(h * 0.55).move_to(front[0].get_right() + LEFT * (h * 0.45))
            tick = VMobject(stroke_color=GOOD, stroke_width=9).set_points_as_corners(
                [[-0.35, 0, 0], [-0.1, -0.28, 0], [0.4, 0.32, 0]])
            ring = Circle(radius=0.5, stroke_color=GOOD, stroke_width=4)
            mark = VGroup(ring, tick).scale_to_fit_height(h * 0.5).move_to(cross)
            self.play(FadeIn(front, shift=UP * 0.4), run_time=each * 0.22)
            self.play(FadeIn(cross, scale=2.4), front[2].animate.set_opacity(0.55), run_time=each * 0.15)
            self.play(Flash(cross, color=BAD, num_lines=10, flash_radius=cross.height * 0.7), run_time=each * 0.12)
            # flip: squash the myth card to a line, then open the fact card from that line
            back.stretch(0.02, 1)
            self.play(VGroup(front, cross).animate.stretch(0.02, 1), run_time=each * 0.13)
            self.remove(front, cross)
            self.play(back.animate.stretch(50, 1), run_time=each * 0.15)
            self.play(Create(ring), Create(tick), run_time=each * 0.15)
        self.wait(max(0.1, total - self.renderer.time))
