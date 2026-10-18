"""Venn diagram: two or three circles slide together, each set's items appear inside it, and the overlap
glows with what they share (comparisons like AI vs ML vs deep learning, or two options side by side)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, FadeIn, Flash, Indicate, Scene, VGroup, Write)  # noqa: E402

from _common import (DOWN, UP, ambient, clean, colors, fit_width, heading, label, load_params, look_of,  # noqa: E402
                     scene_seconds)


class VennDiagramScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        sets = [s for s in p.get("sets", []) if str(s.get("name", "")).strip()][:3]
        if len(sets) < 2:
            raise ValueError("venn_diagram needs two or three sets")
        shared = [clean(x)[:22] for x in p.get("shared", [])][:3]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "venn" + "".join(s["name"] for s in sets))
        title = heading(p.get("title", ""), C, fw, look)
        cy = (title.get_bottom()[1] - fh / 2) / 2 + 0.3
        r = min(fw * 0.27, fh * 0.2)
        d = r * 0.95
        if len(sets) == 2:
            centres = [[-d / 2 - 0.1, cy, 0], [d / 2 + 0.1, cy, 0]]
        else:
            centres = [[d * math.cos(a), cy + d * math.sin(a), 0]
                       for a in (math.pi / 2 + 0.05, math.pi / 2 + 2.15, math.pi / 2 - 2.15)]
            centres = [[c[0] * 0.62, cy + (c[1] - cy) * 0.62, 0] for c in centres]
        palette = [C["primary"], C["accent"], C["text"]]
        circles, labels, items = VGroup(), VGroup(), VGroup()
        for k, (s, c) in enumerate(zip(sets, centres)):
            circ = Circle(radius=r, stroke_color=palette[k], stroke_width=4, fill_color=palette[k],
                          fill_opacity=0.16 if look != "glass" else 0.08).move_to(c)
            circles.add(circ)
            out = [c[0] - 0 if len(sets) == 2 else c[0], c[1], 0]
            name = fit_width(label(s["name"], 30, palette[k]), r * 1.2)
            # the name sits just outside its circle, away from the overlap; the items sit inside, also away from it
            dx, dy = c[0], c[1] - cy
            if len(sets) == 2:
                dx, dy = (-1 if k == 0 else 1), 0.0
            norm = math.hypot(dx, dy) or 1
            ux, uy = dx / norm, dy / norm
            if len(sets) == 2:
                name.next_to(circ, UP, buff=0.15)
            else:
                name.move_to([c[0] + ux * (r + 0.35), c[1] + uy * (r + 0.35), 0])
            labels.add(name)
            its = VGroup(*[label(clean(x)[:18], 20, C["text"], weight="NORMAL") for x in (s.get("items") or [])[:3]])
            if len(its):
                its.arrange(DOWN, buff=0.08)
                fit_width(its, r * 0.62)
                its.move_to([c[0] + ux * r * 0.48, c[1] + uy * r * 0.48, 0])
            items.add(its)
        mid = VGroup(*[label(x, 20, C["text"]) for x in shared])
        if len(mid):
            mid.arrange(DOWN, buff=0.06)
            fit_width(mid, r * 0.55)
            mid.move_to([sum(c[0] for c in centres) / len(centres), sum(c[1] for c in centres) / len(centres), 0])

        self.play(Write(title), run_time=0.6)
        starts = [c.copy().shift((c.get_center() - [0, cy, 0]) * 1.4) for c in circles]
        for c, s in zip(circles, starts):
            c.save_state()
            c.move_to(s.get_center()).set_opacity(0)
        self.play(*[c.animate.restore() for c in circles], run_time=1.0)
        self.play(*[FadeIn(l, shift=DOWN * 0.15) for l in labels], run_time=0.5)
        self.play(*[FadeIn(i, shift=UP * 0.1) for i in items if len(i)], run_time=0.7)
        if len(mid):
            self.play(FadeIn(mid, scale=1.2), Flash(mid.get_center(), color=C["accent"], num_lines=12,
                                                     flash_radius=r * 0.5), run_time=0.7)
        rest = max(0.3, total - self.renderer.time)
        self.play(*[Indicate(c, color=C["accent"], scale_factor=1.03) for c in circles], run_time=rest)
