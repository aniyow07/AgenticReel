"""Chemical reaction: reactants appear, particles flow down the reaction arrow (with the condition above it),
and the products form with a flash while their electrons orbit. Formulas get real subscripts (H2O -> H₂O)."""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arrow, Dot, FadeIn, Flash, GrowArrow, GrowFromCenter, Indicate, Line, RoundedRectangle,  # noqa: E402
                   Scene, Text, VGroup, Write)

from _common import DOWN, LEFT, RIGHT, UP, ambient, clean, colors, fit_width, label, load_params, scene_seconds, stream  # noqa: E402

SUBS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
SUPS = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def formula(s: str) -> str:
    """2H2O -> 2H₂O, SO4^2- -> SO₄²⁻, Ca(OH)2 -> Ca(OH)₂. A leading coefficient stays full size."""
    s = clean(s).replace(" ", "")
    s = re.sub(r"\^\(?([0-9]*[+\-])\)?", lambda m: m.group(1).translate(SUPS), s)
    m = re.match(r"^(\d*)(.*)$", s)
    coef, rest = m.group(1), m.group(2)
    rest = re.sub(r"(?<=[A-Za-z)\]])(\d+)", lambda m: m.group(1).translate(SUBS), rest)
    return (coef + " " if coef else "") + rest


def species_row(items, C, fw, size):
    row = VGroup()
    for i, it in enumerate(items):
        if i:
            row.add(Text("+", font="Segoe UI", font_size=size, color=C["mutedText"]))
        t = Text(formula(it), font="Cambria Math", font_size=size, color=C["text"])
        box = RoundedRectangle(corner_radius=0.16, width=t.width + 0.5, height=t.height + 0.45,
                               stroke_color=C["primary"], stroke_width=4, fill_color=C["surface"], fill_opacity=1)
        t.move_to(box)
        row.add(VGroup(box, t))
    row.arrange(RIGHT, buff=0.25)
    return fit_width(row, fw * 0.9)


def electrons(box, color, n=2, speed=1.4):
    """Small dots orbiting a molecule box so the products feel alive."""
    group = VGroup()
    for k in range(n):
        d = Dot(radius=0.05, color=color)
        d.a = k * 2 * math.pi / n
        rx, ry = box.width / 2 + 0.12, box.height / 2 + 0.12

        def orbit(m, dt, b=box, rx=rx, ry=ry):
            m.a += speed * dt
            c = b.get_center()
            m.move_to([c[0] + rx * math.cos(m.a), c[1] + ry * math.sin(m.a), 0])
        orbit(d, 0)
        d.add_updater(orbit)
        group.add(d)
    return group


class ChemicalReactionScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        reactants = [r for r in p.get("reactants", []) if str(r).strip()][:4]
        products = [r for r in p.get("products", []) if str(r).strip()][:4]
        if not reactants or not products:
            raise ValueError("chemical_reaction needs reactants and products")
        total = scene_seconds(p, 7.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "reaction" + "".join(reactants + products))

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        top = species_row(reactants, C, fw, 44)
        bottom = species_row(products, C, fw, 44)
        arrow_len = min(2.2, fh * 0.28)
        mid_y = (title.get_bottom()[1] - fh / 2) / 2
        top.move_to([0, mid_y + arrow_len / 2 + top.height / 2 + 0.25, 0])
        bottom.move_to([0, mid_y - arrow_len / 2 - bottom.height / 2 - 0.25, 0])
        arrow = Arrow(top.get_bottom() + DOWN * 0.15, bottom.get_top() + UP * 0.15, buff=0, color=C["accent"],
                      stroke_width=7, max_tip_length_to_length_ratio=0.18)
        cond = clean(p.get("condition", ""))
        cond_t = label(cond, 26, C["accent"], weight="NORMAL").next_to(arrow, RIGHT, buff=0.25) if cond else None
        path = Line(arrow.get_start(), arrow.get_end())

        self.play(Write(title), run_time=0.6)
        self.play(*[FadeIn(m, shift=DOWN * 0.2) for m in top], run_time=0.9)
        self.play(GrowArrow(arrow), *( [Write(cond_t)] if cond_t else []), run_time=0.7)
        self.add(stream(path, C["accent"], count=4, speed=0.8, radius=0.08))
        self.wait(0.6)
        boxes = [m for m in bottom if isinstance(m, VGroup)]
        self.play(*[GrowFromCenter(m) for m in bottom], run_time=0.8)
        self.play(*[Flash(b, color=C["accent"], num_lines=10, flash_radius=b.width / 2 + 0.3) for b in boxes],
                  run_time=0.6)
        for b in boxes:
            self.add(electrons(b[0], C["primary"]))
        rest = max(0.4, total - 0.6 - 0.9 - 0.7 - 0.6 - 0.8 - 0.6)
        self.play(*[Indicate(b, color=C["accent"], scale_factor=1.05) for b in boxes], run_time=rest)
