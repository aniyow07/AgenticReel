"""Network / graph: nodes pop in on a circle (or in layers for a neural network), edges draw between them,
then a pulse travels along the given path and lights each node it reaches (a route, a BFS order, a
packet path, a forward pass)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arrow, Circle, Create, Dot, FadeIn, Flash, GrowFromCenter, Line, MoveAlongPath, Scene,  # noqa: E402
                   VGroup, Write)

from _common import DOWN, UP, ambient, clean, colors, fit_width, label, load_params, scene_seconds  # noqa: E402


class NodeGraphScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        names = [clean(n)[:14] for n in p.get("nodes", [])][:10]
        idx = {n.lower(): i for i, n in enumerate(names)}
        find = lambda v: v if isinstance(v, int) else idx.get(str(v).strip().lower())  # noqa: E731
        edges = [(find(a), find(b)) for a, b in (p.get("edges") or [])]
        edges = [(a, b) for a, b in edges if a is not None and b is not None and a != b and a < len(names) and b < len(names)]
        path = [i for i in (find(v) for v in (p.get("path") or [])) if i is not None]
        layers = [int(x) for x in (p.get("layers") or [])]
        directed = bool(p.get("directed"))
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "graph" + "".join(names))
        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        cy = (title.get_bottom()[1] - fh / 2) / 2

        pos = []
        if layers and sum(layers) == len(names):  # left-to-right layers (a small neural network)
            k = 0
            for li, count in enumerate(layers):
                x = -fw * 0.36 + fw * 0.72 * li / max(1, len(layers) - 1)
                for j in range(count):
                    pos.append([x, cy + (j - (count - 1) / 2) * min(1.3, fh * 0.5 / max(count, 1)), 0])
                    k += 1
        else:
            R = min(fw * 0.36, fh * 0.26)
            for i in range(len(names)):
                a = math.pi / 2 - 2 * math.pi * i / max(1, len(names))
                pos.append([R * math.cos(a), cy + R * math.sin(a), 0])

        r = 0.42 if len(names) <= 6 else 0.34
        nodes = VGroup()
        for i, n in enumerate(names):
            c = Circle(radius=r, stroke_color=C["primary"], stroke_width=4, fill_color=C["surface"], fill_opacity=1)
            t = fit_width(label(n, 20, C["text"]), r * 1.7)
            nodes.add(VGroup(c, t).move_to(pos[i]))
        lines = VGroup()
        for a, b in edges:
            A, B = nodes[a][0], nodes[b][0]
            d = [B.get_center()[0] - A.get_center()[0], B.get_center()[1] - A.get_center()[1], 0]
            L = math.hypot(d[0], d[1]) or 1
            s = [A.get_center()[0] + d[0] / L * r, A.get_center()[1] + d[1] / L * r, 0]
            e = [B.get_center()[0] - d[0] / L * r, B.get_center()[1] - d[1] / L * r, 0]
            lines.add(Arrow(s, e, buff=0, color=C["mutedText"], stroke_width=3, max_tip_length_to_length_ratio=0.12)
                      if directed else Line(s, e, color=C["mutedText"], stroke_width=3))

        self.play(Write(title), run_time=0.6)
        self.play(*[GrowFromCenter(nd) for nd in nodes], run_time=0.8)
        self.play(*[Create(l) for l in lines], run_time=0.8)
        self.add_foreground_mobjects(*nodes)

        budget = max(1.0, total - 2.2 - 0.6)
        if len(path) >= 2:
            each = budget / len(path)
            nodes[path[0]][0].set_stroke(C["accent"]).set_fill(C["accent"], 0.35)
            self.play(Flash(nodes[path[0]], color=C["accent"], flash_radius=r + 0.2), run_time=min(0.5, each))
            for a, b in zip(path, path[1:]):
                pulse = Dot(radius=0.11, color=C["accent"]).move_to(nodes[a].get_center())
                hop = Line(nodes[a].get_center(), nodes[b].get_center())
                self.add(pulse)
                self.play(MoveAlongPath(pulse, hop), run_time=each * 0.65)
                self.remove(pulse)
                nodes[b][0].set_stroke(C["accent"]).set_fill(C["accent"], 0.35)
                self.play(Flash(nodes[b], color=C["accent"], flash_radius=r + 0.2, num_lines=8), run_time=each * 0.35)
        else:
            for nd in nodes:
                self.play(nd[0].animate.set_stroke(C["accent"]), run_time=budget / max(1, len(nodes)))
        self.wait(max(0.3, total - self.renderer.time))
