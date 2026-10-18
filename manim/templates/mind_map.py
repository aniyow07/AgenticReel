"""Mind map: a central idea, branches that grow out to its main parts, and small leaves on each branch
(an overview of a topic, the pillars of a subject, causes and effects)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, Create, CubicBezier, FadeIn, GrowFromCenter, Indicate, Scene, VGroup, Write)  # noqa: E402

from _common import (DOWN, ambient, card, clean, colors, fit_width, heading, label, load_params, look_of,  # noqa: E402
                     scene_seconds)


class MindMapScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        branches = [b for b in p.get("branches", []) if str(b.get("name", "")).strip()][:6]
        if len(branches) < 2:
            raise ValueError("mind_map needs at least two branches")
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "mind" + "".join(b["name"] for b in branches))
        title = heading(p.get("title", ""), C, fw, look)
        cy = (title.get_bottom()[1] - fh / 2) / 2
        hub_r = min(1.1, fw * 0.17)
        hub = VGroup(Circle(radius=hub_r, stroke_color=C["accent"], stroke_width=5, fill_color=C["surface"],
                            fill_opacity=1),
                     fit_width(label(p.get("center", "") or "Topic", 28, C["text"]), hub_r * 1.7)).move_to([0, cy, 0])
        R = min(fw * 0.36, fh * 0.28)
        palette = [C["primary"], C["accent"]]
        nodes, links, leaves = [], [], []
        for k, b in enumerate(branches):
            a = math.pi / 2 - 2 * math.pi * k / len(branches) + 0.25
            end = [R * math.cos(a), cy + R * math.sin(a) * 1.15, 0]
            node = card(b["name"], C, min(2.4, fw * 0.36), look, palette[k % 2], size=24).move_to(end)
            start = [hub_r * math.cos(a), cy + hub_r * math.sin(a), 0]
            mid1 = [start[0] * 1.6, start[1] + (end[1] - start[1]) * 0.2, 0]
            mid2 = [end[0] * 0.7, end[1], 0]
            links.append(CubicBezier(start, mid1, mid2, node.get_center(), color=palette[k % 2], stroke_width=5))
            nodes.append(node)
            lv = VGroup(*[label(clean(x)[:16], 18, C["mutedText"], weight="NORMAL") for x in (b.get("items") or [])[:2]])
            if len(lv):
                lv.arrange(DOWN, buff=0.04)
                out = 1 if math.sin(a) >= 0 else -1
                lv.next_to(node, [0, out, 0], buff=0.12)
                fit_width(lv, fw * 0.36)
            leaves.append(lv)
        self.play(Write(title), GrowFromCenter(hub), run_time=0.8)
        grow = max(1.0, (total - 2.0) * 0.6)
        for link, node, lv in zip(links, nodes, leaves):
            self.play(Create(link), FadeIn(node, scale=0.7), *([FadeIn(lv)] if len(lv) else []),
                      run_time=grow / len(nodes))
        self.add_foreground_mobjects(hub, *nodes)
        rest = max(0.3, total - self.renderer.time)
        self.play(Indicate(hub[0], color=C["accent"], scale_factor=1.08), run_time=rest)
