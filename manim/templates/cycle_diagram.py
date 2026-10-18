"""Cycle: stages sit around a ring (water cycle, product life cycle, a feedback loop); curved arrows chase
each other round it and each stage lights up as the loop reaches it, with the centre naming the cycle."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (ArcBetweenPoints, Create, FadeIn, Flash, GrowFromCenter, Indicate, Scene, VGroup, Write)  # noqa: E402

from _common import (ambient, card, colors, fit_width, heading, label, load_params, look_of,  # noqa: E402
                     scene_seconds, stream)


class CycleDiagramScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        stages = [s for s in p.get("stages", []) if str(s).strip()][:6]
        if len(stages) < 3:
            raise ValueError("cycle_diagram needs at least three stages")
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "cycle" + "".join(stages))
        title = heading(p.get("title", ""), C, fw, look)
        R = min(fw * 0.34, fh * 0.26)
        cy = (title.get_bottom()[1] - fh / 2) / 2
        w = min(2.3, fw * 0.32)
        nodes, pos = VGroup(), []
        for k, s in enumerate(stages):
            a = math.pi / 2 - 2 * math.pi * k / len(stages)
            pt = [R * math.cos(a), cy + R * math.sin(a), 0]
            pos.append(pt)
            nodes.add(card(s, C, w, look, C["primary"] if k % 2 == 0 else C["accent"], size=24).move_to(pt))
        centre = fit_width(label(p.get("center", "") or "", 28, C["accent"]), R * 0.8).move_to([0, cy, 0])
        arcs = []
        for k in range(len(stages)):
            a0 = math.pi / 2 - 2 * math.pi * (k + 0.28) / len(stages)
            a1 = math.pi / 2 - 2 * math.pi * (k + 0.72) / len(stages)
            arcs.append(ArcBetweenPoints([R * math.cos(a0), cy + R * math.sin(a0), 0],
                                         [R * math.cos(a1), cy + R * math.sin(a1), 0],
                                         angle=-0.6, color=C["accent"], stroke_width=6).add_tip(tip_length=0.22))
        self.play(Write(title), run_time=0.6)
        self.play(*[GrowFromCenter(n) for n in nodes], *( [FadeIn(centre)] if len(centre) else []), run_time=0.9)
        self.play(*[Create(a) for a in arcs], run_time=0.8)
        for a in arcs:
            self.add(stream(a, C["accent"], count=1, speed=0.7))
        each = max(0.3, (total - 2.3) / (len(stages) * 1.5))
        k = 0
        while self.renderer.time < total - each:
            n = nodes[k % len(nodes)]
            self.play(Indicate(n[0], color=C["accent"], scale_factor=1.08),
                      Flash(n.get_center(), color=C["accent"], num_lines=8, flash_radius=w / 2), run_time=each)
            k += 1
