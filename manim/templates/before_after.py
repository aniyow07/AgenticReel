"""Split-screen comparison for any two things. "versus": a divider grows down the middle, a VS badge spins in
and the two sides' points arrive in turn. "before_after": the before side shows first, then a sweeping
wipe carries the eye across to the after side, which lights up while the before side fades back."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arrow, Circle, Create, DashedVMobject, FadeIn, Flash, GrowFromCenter, Line, Rectangle,  # noqa: E402
                   RoundedRectangle, Scene, SpinInFromNothing, VGroup, Write)

from _common import (DOWN, LEFT, RIGHT, UP, ambient, card, clean, colors, fit_width, heading, label,  # noqa: E402
                     load_params, look_of, scene_seconds, wrap)


class BeforeAfterScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        mode = p.get("mode") if p.get("mode") in ("versus", "before_after") else "versus"
        names = [clean(p.get("left_title") or ("Before" if mode == "before_after" else "A"))[:24],
                 clean(p.get("right_title") or ("After" if mode == "before_after" else "B"))[:24]]
        sides = [[clean(x)[:40] for x in p.get(k) or [] if str(x).strip()][:4] for k in ("left_points", "right_points")]
        ambient(self, C, "before_after" + "".join(names))
        title = heading(p.get("title", ""), C, fw, look)
        verdict = clean(p.get("verdict", ""))[:40]

        top = title.get_bottom()[1] - 0.35
        bottom = -fh / 2 + (1.25 if verdict else 0.45)
        pw = fw * 0.45
        cols = [C["primary"], C["accent"]]
        panels, heads, rows = [], [], []
        for s in (0, 1):
            x = (-1 if s == 0 else 1) * (fw * 0.25)
            panel = RoundedRectangle(corner_radius=0.2, width=pw, height=top - bottom, stroke_width=0 if look != "glass" else 1.5,
                                     stroke_color=C["text"], stroke_opacity=0.4, fill_color=cols[s],
                                     fill_opacity=0.12).move_to([x, (top + bottom) / 2, 0])
            h = fit_width(label(names[s], 34, cols[s]), pw * 0.85).move_to([x, top - 0.45, 0])
            items = VGroup()
            for t in sides[s]:
                items.add(card(wrap(t, 16, 2), C, pw * 0.86, look, cols[s], size=22, min_h=0.7))
            if len(items):
                items.arrange(DOWN, buff=0.18)
                room = (top - 1.0) - (bottom + 0.2)
                if items.height > room:
                    items.scale_to_fit_height(room)
                items.move_to([x, (top - 1.0 + bottom + 0.2) / 2, 0])
            panels.append(panel)
            heads.append(h)
            rows.append(items)
        foot = None
        if verdict:
            foot = card(verdict, C, fw * 0.8, "pill", C["accent"], size=26).move_to([0, -fh / 2 + 0.65, 0])

        self.play(Write(title), run_time=0.5)
        steps = max(len(rows[0]), len(rows[1]))
        if mode == "versus":
            divider = Line([0, top, 0], [0, bottom, 0], color=C["text"], stroke_width=3, stroke_opacity=0.6)
            mid = [0, (top + bottom) / 2, 0]
            badge = VGroup(Circle(radius=0.42, fill_color=C["accent"], fill_opacity=1, stroke_width=0),
                           label("VS", 26, C["background"])).move_to(mid)
            ring = DashedVMobject(Circle(radius=0.56, stroke_color=C["accent"], stroke_width=3), num_dashes=14)
            ring.move_to(mid).add_updater(lambda m, dt: m.rotate(1.2 * dt))
            self.play(Create(divider), FadeIn(panels[0], shift=RIGHT * 0.8), FadeIn(panels[1], shift=LEFT * 0.8),
                      run_time=0.6)
            self.play(SpinInFromNothing(badge), FadeIn(ring), FadeIn(heads[0], shift=DOWN * 0.3), FadeIn(heads[1], shift=DOWN * 0.3),
                      run_time=0.6)
            each = max(0.25, (total - 3.0) / max(1, steps))
            for k in range(steps):
                anims = [FadeIn(r[k], shift=(RIGHT if s == 0 else LEFT) * 0.5) for s, r in enumerate(rows) if k < len(r)]
                self.play(*anims, run_time=each)
            if foot:
                self.play(FadeIn(foot, shift=UP * 0.4), Flash(badge, color=C["accent"]), run_time=0.5)
            self.play(badge.animate.scale(1.12), run_time=0.25)
            self.play(badge.animate.scale(1 / 1.12), run_time=0.25)
        else:
            each = max(0.2, (total - 3.6) / max(1, len(rows[0]) + len(rows[1])))
            self.play(FadeIn(panels[0], shift=RIGHT * 0.5), FadeIn(heads[0]), run_time=0.5)
            for r in rows[0]:
                self.play(FadeIn(r, shift=UP * 0.2), run_time=each)
            # the wipe: a bright bar sweeps across and leaves the after side lit behind it
            bar = Rectangle(width=0.18, height=top - bottom, stroke_width=0, fill_color=C["accent"],
                            fill_opacity=0.9).move_to([-fw * 0.02, (top + bottom) / 2, 0])
            arrow = Arrow(LEFT * 0.5, RIGHT * 0.5, color=C["accent"], stroke_width=8, buff=0).move_to(
                [0, (top + bottom) / 2, 0])
            self.play(GrowFromCenter(bar), run_time=0.3)
            self.play(bar.animate.move_to([fw / 2 + 0.3, (top + bottom) / 2, 0]), FadeIn(panels[1], shift=RIGHT * 0.3),
                      FadeIn(heads[1]), VGroup(heads[0], rows[0]).animate.set_opacity(0.4),
                      panels[0].animate.set_fill(opacity=0.05),
                      run_time=0.7)
            self.remove(bar)
            self.play(GrowFromCenter(arrow), run_time=0.3)
            for r in rows[1]:
                self.play(FadeIn(r, shift=UP * 0.2), run_time=each)
            if foot:
                self.play(FadeIn(foot, shift=UP * 0.4), run_time=0.4)
            self.play(Flash(heads[1], color=C["accent"], flash_radius=heads[1].width / 2 + 0.2), run_time=0.4)
        self.wait(max(0.1, total - self.renderer.time))
