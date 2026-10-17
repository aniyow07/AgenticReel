"""Step-by-step equation: each line morphs out of the one above it (matching symbols glide into place),
with a short note for what changed, and the final line is boxed. Plain Text only, no LaTeX needed."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Create, FadeIn, Flash, Indicate, Scene, SurroundingRectangle, Text,  # noqa: E402
                   TransformMatchingShapes, VGroup, Write)

from _common import DOWN, UP, ambient, clean, colors, fit_width, label, load_params, scene_seconds  # noqa: E402

MATH_FONT = "Cambria Math"
SUPERS = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")


def pretty(expr: str) -> str:
    """Write math the way it is printed: x^2 -> x², * -> ×, sqrt -> √, <= -> ≤ ..."""
    s = clean(expr)
    s = re.sub(r"\^\(?([0-9n+\-]{1,3})\)?", lambda m: m.group(1).translate(SUPERS), s)
    s = re.sub(r"sqrt\s*", "√", s, flags=re.I)
    for a, b in (("<=", "≤"), (">=", "≥"), ("!=", "≠"), ("->", "→"), ("*", "×"), ("+-", "±")):
        s = s.replace(a, b)
    s = re.sub(r"\bpi\b", "π", s)
    return s


class EquationStepsScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        lines = [pretty(x) for x in p.get("lines", []) if str(x).strip()][:6]
        if len(lines) < 2:
            raise ValueError("equation_steps needs at least two lines")
        notes = [clean(n) for n in (p.get("notes") or [])]
        if len(notes) >= len(lines):  # a note per line (the first is usually "start"): keep the ones for each step
            notes = notes[len(notes) - len(lines) + 1:]
        notes = notes[:len(lines) - 1]
        total = scene_seconds(p, 7.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "equation" + "".join(lines))

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        eqs = [fit_width(Text(s, font=MATH_FONT, font_size=54, color=C["text"]), fw * 0.86) for s in lines]
        # notes sit between two lines: "↓ subtract 3"
        gaps = [Text(("↓ " + notes[i]) if i < len(notes) and notes[i] else "↓", font="Segoe UI", font_size=24,
                     color=C["accent"]) for i in range(len(lines) - 1)]
        stack = VGroup()
        for i, e in enumerate(eqs):
            stack.add(e)
            if i < len(gaps):
                stack.add(fit_width(gaps[i], fw * 0.8))
        stack.arrange(DOWN, buff=0.28)
        room = fh - title.height - 1.2
        if stack.height > room:
            stack.scale_to_fit_height(room)
        stack.move_to([0, (title.get_bottom()[1] - fh / 2) / 2, 0])

        self.play(Write(title), run_time=0.6)
        self.play(Write(eqs[0]), run_time=0.9)
        build = max(1.0, (total - 1.5) * 0.75)
        each = build / (len(lines) - 1)
        for i in range(1, len(lines)):
            gap = gaps[i - 1]
            self.play(FadeIn(gap, shift=DOWN * 0.15), eqs[i - 1].animate.set_color(C["mutedText"]), run_time=each * 0.3)
            self.play(TransformMatchingShapes(eqs[i - 1].copy(), eqs[i]), run_time=each * 0.7)
        box = SurroundingRectangle(eqs[-1], color=C["accent"], buff=0.18, corner_radius=0.12, stroke_width=5)
        self.play(Create(box), Flash(box.get_top(), color=C["accent"], num_lines=10, flash_radius=0.4),
                  run_time=0.5)
        rest = max(0.3, total - 0.6 - 0.9 - build - 0.5)
        self.play(Indicate(eqs[-1], color=C["accent"], scale_factor=1.08), run_time=rest)
