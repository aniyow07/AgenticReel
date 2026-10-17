"""Cybersecurity: an attack travels from the attacker towards the target. With a defence in the way the
packets hit the shield and bounce off (blocked); without one, or with outcome "breached", they get through
and the target raises an alert. Optional "encrypted" draws locks on the legitimate traffic."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, Create, Dot, FadeIn, Flash, Indicate, Line, MoveAlongPath, RegularPolygon,  # noqa: E402
                   RoundedRectangle, Scene, Square, VGroup, Wiggle, Write)

from _common import DOWN, UP, ambient, colors, fit_width, label, load_params, scene_seconds  # noqa: E402

DANGER = "#FF5A5F"


def box(text, C, stroke, w, size=24, sub=""):
    r = RoundedRectangle(corner_radius=0.18, width=w, height=0.95 if sub else 0.75, stroke_color=stroke,
                         stroke_width=4, fill_color=C["surface"], fill_opacity=1)
    t = fit_width(label(text, size, C["text"]), w - 0.3)
    g = VGroup(r, t)
    if sub:
        s = fit_width(label(sub, 18, C["mutedText"], weight="NORMAL"), w - 0.3)
        VGroup(t, s).arrange(DOWN, buff=0.06).move_to(r)
        g.add(s)
    else:
        t.move_to(r)
    return g


def lock(color):
    body = Square(side_length=0.16, stroke_width=0, fill_color=color, fill_opacity=1)
    shackle = Circle(radius=0.06, stroke_color=color, stroke_width=3).next_to(body, UP, buff=-0.05)
    return VGroup(shackle, body)


class SecurityFlowScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        attack = p.get("attack", "") or "Attack"
        defense = p.get("defense", "")
        outcome = p.get("outcome", "blocked" if defense else "breached")
        ambient(self, C, "security" + attack + defense + outcome)

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        w = min(3.2, fw * 0.6)
        attacker = box(p.get("attacker", "") or "Attacker", C, DANGER, w, sub=attack)
        target = box(p.get("target", "") or "Server", C, C["primary"], w)
        top_y = title.get_bottom()[1] - 0.9
        attacker.move_to([0, top_y - 0.5, 0])
        target.move_to([0, -fh / 2 + 1.4, 0])
        path = Line(attacker.get_bottom(), target.get_top(), color=C["mutedText"], stroke_width=3, stroke_opacity=0.6)
        shield = None
        if defense:
            hexa = RegularPolygon(n=6, color=C["accent"], fill_color=C["surface"], fill_opacity=1, stroke_width=5)
            hexa.scale_to_fit_width(min(2.6, fw * 0.5)).stretch_to_fit_height(0.95)
            shield = VGroup(hexa, fit_width(label(defense, 24, C["text"]), hexa.width - 0.4))
            shield.move_to(path.point_from_proportion(0.5))

        self.play(Write(title), FadeIn(attacker, shift=DOWN * 0.2), FadeIn(target, shift=UP * 0.2), run_time=0.9)
        self.play(Create(path), *([FadeIn(shield, scale=0.8)] if shield else []), run_time=0.6)

        if p.get("encrypted"):  # legitimate traffic first: locked packets pass straight through
            safe = VGroup(Dot(radius=0.09, color=C["primary"]), lock(C["primary"]).shift(UP * 0.18))
            safe.move_to(path.get_start())
            self.add(safe)
            self.play(MoveAlongPath(safe, path), run_time=0.9)
            self.remove(safe)

        waves = 3
        budget = max(1.5, total - 1.5 - (0.9 if p.get("encrypted") else 0) - 1.2)
        each = budget / waves
        stop = 0.5 if shield and outcome == "blocked" else 1.0
        for k in range(waves):
            pk = Dot(radius=0.11, color=DANGER).move_to(path.get_start())
            seg = Line(path.get_start(), path.point_from_proportion(stop * 0.97))
            self.add(pk)
            self.play(MoveAlongPath(pk, seg), run_time=each * 0.6)
            if shield and outcome == "blocked":
                back = Line(pk.get_center(), path.point_from_proportion(0.2))
                self.play(Flash(pk.get_center(), color=C["accent"], num_lines=10, flash_radius=0.45),
                          Indicate(shield, color=C["accent"], scale_factor=1.06), MoveAlongPath(pk, back),
                          run_time=each * 0.4)
            else:
                self.play(Flash(target.get_top(), color=DANGER, num_lines=8), run_time=each * 0.4)
            self.remove(pk)

        if outcome == "blocked":
            verdict = label("Blocked", 34, C["accent"])
        else:
            verdict = label("Breach detected", 34, DANGER)
            self.play(target[0].animate.set_stroke(DANGER), Wiggle(target), run_time=0.6)
        verdict.next_to(target, UP, buff=0.3)
        if shield and verdict.get_top()[1] > shield.get_bottom()[1] - 0.1:
            verdict.next_to(target, DOWN, buff=0.2)
        self.play(FadeIn(verdict, scale=1.2), run_time=0.6)
        self.wait(0.2)
