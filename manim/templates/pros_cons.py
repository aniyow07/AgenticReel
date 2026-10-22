"""Pros and cons on a balance scale: each point appears in its column while a weight drops onto that side's
pan and the beam tips toward the heavier side, settling on the verdict (pros, cons or even)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, Arc, Dot, FadeIn, Flash, Line, Polygon, RoundedRectangle, Scene, ValueTracker,  # noqa: E402
                   VGroup, Write, rate_functions)

from _common import (BAD, DOWN, GOOD, LEFT, RIGHT, UP, ambient, card, clean, colors, fit_width, heading,  # noqa: E402
                     label, load_params, look_of, scene_seconds, wrap)


class ProsConsScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        pros = [clean(x)[:40] for x in p.get("pros") or [] if str(x).strip()][:4]
        cons = [clean(x)[:40] for x in p.get("cons") or [] if str(x).strip()][:4]
        if not pros or not cons:
            raise ValueError("pros_cons needs at least one pro and one con")
        verdict = p.get("verdict")
        if verdict not in ("pros", "cons", "even"):
            verdict = "pros" if len(pros) > len(cons) else "cons" if len(cons) > len(pros) else "even"
        names = [clean(p.get("pros_label") or "Pros")[:20], clean(p.get("cons_label") or "Cons")[:20]]
        ambient(self, C, "proscons" + "".join(pros + cons))
        title = heading(p.get("title", ""), C, fw, look)

        # the scale: a post, a beam that turns on its tip, and pans hanging from the beam's ends
        pivot = [0, title.get_bottom()[1] - 0.75, 0]
        arm = fw * 0.27
        post = VGroup(Line(pivot, [0, pivot[1] - 1.55, 0], color=C["mutedText"], stroke_width=6),
                      Polygon([-0.45, pivot[1] - 1.75, 0], [0.45, pivot[1] - 1.75, 0], [0, pivot[1] - 1.45, 0],
                              stroke_width=0, fill_color=C["mutedText"], fill_opacity=1),
                      Dot(pivot, radius=0.1, color=C["accent"]))
        tilt = ValueTracker(0)

        def beam_end(side):  # side -1 = left (pros), +1 = right (cons)
            a = tilt.get_value()
            return [pivot[0] + side * arm * math.cos(a), pivot[1] + side * arm * math.sin(a), 0]  # a > 0 drops the left pan

        beam = Line(beam_end(-1), beam_end(1), color=C["text"], stroke_width=7)
        beam.add_updater(lambda m: m.put_start_and_end_on(beam_end(-1), beam_end(1)))
        cols = [GOOD, BAD]
        pans = []
        for k, side in enumerate((-1, 1)):
            hang = 0.9
            a0 = beam_end(side)
            strings = VGroup(Line(a0, [a0[0] - 0.42, a0[1] - hang, 0], color=C["mutedText"], stroke_width=2),
                             Line(a0, [a0[0] + 0.42, a0[1] - hang, 0], color=C["mutedText"], stroke_width=2))
            dish = Arc(radius=0.55, start_angle=math.pi, angle=math.pi, color=cols[k], stroke_width=6)
            dish.move_to([a0[0], a0[1] - hang - 0.2, 0])
            pan = VGroup(strings, dish)
            pan.anchor = a0
            pan.stack = 0

            def follow(m, side=side):
                e = beam_end(side)
                m.shift([e[0] - m.anchor[0], e[1] - m.anchor[1], 0])
                m.anchor = e
            pan.add_updater(follow)
            pans.append(pan)
        heads = [fit_width(label(names[k], 30, cols[k]), fw * 0.4) for k in (0, 1)]
        col_top = pivot[1] - 2.15
        for k, side in enumerate((-1, 1)):
            heads[k].move_to([side * fw * 0.25, col_top, 0])
        items = []
        for k, pts in enumerate((pros, cons)):
            g = VGroup(*[card(wrap(t, 18, 2), C, fw * 0.42, look, cols[k], size=20, min_h=0.6) for t in pts])
            g.arrange(DOWN, buff=0.14).next_to(heads[k], DOWN, buff=0.22)
            room = heads[k].get_bottom()[1] - 0.22 - (-fh / 2 + 0.3)
            if g.height > room:
                g.scale_to_fit_height(room).next_to(heads[k], DOWN, buff=0.22)
            items.append(list(g))

        self.play(Write(title), FadeIn(post), run_time=0.5)
        self.add(beam, *pans)
        self.play(FadeIn(beam), *[FadeIn(pn) for pn in pans], FadeIn(heads[0]), FadeIn(heads[1]), run_time=0.5)
        order = [(k, i) for i in range(4) for k in (0, 1) if i < len(items[k])]
        each = max(0.25, (total - 2.6) / len(order))
        score = 0
        for k, i in order:
            pan = pans[k]
            w = RoundedRectangle(corner_radius=0.05, width=0.42, height=0.2, stroke_width=0, fill_color=cols[k],
                                 fill_opacity=1)
            w.move_to(pan[1].get_bottom() + UP * (0.13 + 0.22 * pan.stack))
            pan.stack += 1
            score += 1 if k == 0 else -1
            target = max(-14, min(14, 6 * score)) * DEGREES
            self.play(FadeIn(items[k][i], shift=(RIGHT if k == 0 else LEFT) * 0.4),
                      FadeIn(w, shift=DOWN * 1.2), run_time=each * 0.55)
            pan.add(w)
            self.play(tilt.animate.set_value(target), run_time=each * 0.45, rate_func=rate_functions.ease_out_back)
        final = {"pros": 12, "cons": -12, "even": 0}[verdict] * DEGREES
        self.play(tilt.animate.set_value(final), run_time=0.6, rate_func=rate_functions.ease_out_bounce)
        if verdict != "even":
            win = heads[0 if verdict == "pros" else 1]
            self.play(Flash(win, color=win.get_color(), flash_radius=win.width / 2 + 0.25, num_lines=14),
                      win.animate.scale(1.15), run_time=0.5)
        self.wait(max(0.1, total - self.renderer.time))
