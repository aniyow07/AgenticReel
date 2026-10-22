"""A decision as a branching tree: the question card drops in, branches grow down to each choice and its
outcome, then a pulse runs down the chosen path, which lights up while the other branches dim."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, Create, CubicBezier, FadeIn, Flash, Scene, VGroup, Write)  # noqa: E402

from _common import (DOWN, RIGHT, UP, ambient, card, clean, colors, heading, label, load_params, look_of,  # noqa: E402
                     mix, scene_seconds, stream, wrap)


def branch(a, b, col: str, width: float = 4):
    mid = (a[1] + b[1]) / 2
    return CubicBezier(a, [a[0], mid, 0], [b[0], mid, 0], b, stroke_color=col, stroke_width=width)


class DecisionTreeScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        question = clean(p.get("question", ""))[:60]
        opts = [(clean(o.get("choice", ""))[:24], clean(o.get("outcome", ""))[:40]) for o in p.get("options") or []
                if isinstance(o, dict) and str(o.get("choice", "")).strip()][:3]
        if not question or len(opts) < 2:
            raise ValueError("decision_tree needs a question and at least two options")
        picked = p.get("picked")
        picked = picked if isinstance(picked, int) and 0 <= picked < len(opts) else None
        ambient(self, C, "decision" + question)
        title = heading(p.get("title", ""), C, fw, look) if str(p.get("title", "")).strip() else VGroup()
        top = (title.get_bottom()[1] if len(title) else fh / 2) - 0.35
        n = len(opts)
        q = card(wrap(question, 26, 2), C, fw * 0.8, look, C["accent"], size=26, min_h=0.9)
        q.move_to([0, top - q.height / 2, 0])
        badge = VGroup(Circle(radius=0.3, fill_color=C["accent"], fill_opacity=1, stroke_width=0),
                       label("?", 30, C["background"])).move_to(q.get_corner(UP + RIGHT) + [-0.15, -0.05, 0])
        colw = fw * 0.92 / n
        xs = [-fw * 0.46 + colw * (i + 0.5) for i in range(n)]
        y_choice = q.get_bottom()[1] - 1.3
        y_out = -fh / 2 + 1.0
        choices, outs, links1, links2 = [], [], [], []
        for i, (ch, out) in enumerate(opts):
            col = mix(C["primary"], C["accent"], i / max(1, n - 1))
            c = card(ch, C, colw * 0.86, "pill" if look != "underline" else look, col, size=24).move_to([xs[i], y_choice, 0])
            choices.append(c)
            links1.append(branch(q.get_bottom(), c.get_top(), col))
            if out:
                o = card(wrap(out, 14, 3), C, colw * 0.9, look, col, size=20, min_h=0.9).move_to([xs[i], y_out, 0])
                outs.append(o)
                links2.append(branch(c.get_bottom(), o.get_top(), col, 3))
            else:
                outs.append(None)
                links2.append(None)

        self.play(*([Write(title)] if len(title) else []), FadeIn(q, shift=DOWN * 0.5), run_time=0.5)
        self.play(FadeIn(badge, scale=2), run_time=0.25)
        grow = max(0.4, (total - 3.0) / 2)
        self.play(*[Create(l) for l in links1], *[FadeIn(c, shift=DOWN * 0.3) for c in choices], run_time=grow)
        self.play(*[Create(l) for l in links2 if l], *[FadeIn(o, shift=DOWN * 0.3) for o in outs if o],
                  run_time=grow)
        if picked is not None:
            path = [links1[picked]] + ([links2[picked]] if links2[picked] else [])
            pulses = VGroup(*[stream(l, C["accent"], count=2, speed=0.9, radius=0.09) for l in path])
            dim = [m for i in range(n) if i != picked for m in (links1[i], choices[i], links2[i], outs[i]) if m]
            self.add(pulses)
            self.play(*[m.animate.set_opacity(0.3) for m in dim],
                      *[l.animate.set_stroke(C["accent"], 7) for l in path], run_time=0.6)
            last = outs[picked] or choices[picked]
            self.play(Flash(last, color=C["accent"], flash_radius=last.width / 2 + 0.2, num_lines=14),
                      last.animate.scale(1.08), run_time=0.5)
        else:
            pulses = VGroup(*[stream(l, C["accent"], count=2, speed=0.7, radius=0.07) for l in links1 + links2 if l])
            self.add(pulses)
        self.wait(max(0.1, total - self.renderer.time))
