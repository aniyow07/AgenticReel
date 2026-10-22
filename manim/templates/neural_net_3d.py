"""3D neural network: layers of neurons stand as grids in depth, connections draw between them, signals pulse
forward, and the camera flies along the network from the first layer to the last."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, LEFT, PI, RIGHT, Create, Dot, FadeIn, GrowFromCenter, LaggedStart, Line, Text,  # noqa: E402
                   ThreeDScene, VGroup, interpolate_color, ManimColor)

from _common import FONT, clean, colors, load_params, look_of, overlay, scene_seconds, show, stream  # noqa: E402


class NeuralNet3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:24] for x in p.get("layers", []) if str(x).strip()][:5]
        if len(names) < 2:
            raise ValueError("neural_net_3d needs at least two layers")
        n = len(names)
        gap = 2.3
        xs = [(i - (n - 1) / 2) * gap for i in range(n)]
        sides = [4] + [3] * (n - 2) + [2] if n > 2 else [3, 2]
        self.set_camera_orientation(phi=72 * DEGREES, theta=-115 * DEGREES, zoom=min(1.0, fw / 6.5))
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        rng = random.Random("nn" + "".join(names))
        lo, hi = ManimColor(C["primary"]), ManimColor(C["accent"])

        layers, tags = [], VGroup()
        for i, (x, s) in enumerate(zip(xs, sides)):
            col = interpolate_color(lo, hi, i / max(1, n - 1))
            step = 0.62
            grid = VGroup(*[Dot([x, (a - (s - 1) / 2) * step, (b - (s - 1) / 2) * step], radius=0.12, color=col)
                            for a in range(s) for b in range(s)])
            layers.append(grid)
            t = Text(names[i], font=FONT, font_size=26, color=C["text"], weight="BOLD")
            if t.width > gap * 0.9:
                t.scale_to_fit_width(gap * 0.9)
            t.rotate(PI / 2, axis=RIGHT).move_to([x, 0, -1.55])
            tags.add(t)
        links = VGroup()
        for a, b in zip(layers, layers[1:]):
            for d in a:
                for e in rng.sample(list(b), k=min(3, len(b))):
                    links.add(Line(d.get_center(), e.get_center(), stroke_width=1.3, stroke_color=C["mutedText"],
                                   stroke_opacity=0.35))
        nodes = [d for g in layers for d in g]
        self.add_fixed_orientation_mobjects(*nodes)
        # the camera "flies" along the network by sliding the network past it (moving the camera's frame
        # centre would also drag the pinned title off screen)
        net = VGroup(*layers, tags, links).shift(LEFT * xs[0])

        self.play(*show(title), LaggedStart(*[GrowFromCenter(g) for g in layers], lag_ratio=0.25),
                  FadeIn(tags), run_time=1.0)
        self.play(Create(links), *show(*notes), run_time=0.8)
        pulses = VGroup(*[stream(ln, C["accent"], count=1, speed=0.8 + 0.4 * rng.random(), radius=0.05)
                          for ln in rng.sample(list(links), k=min(18, len(links)))])
        self.add(pulses)
        fly = max(1.0, total - self.renderer.time - 0.3)
        self.move_camera(theta=-65 * DEGREES, phi=66 * DEGREES, run_time=fly,
                         added_anims=[net.animate.shift(LEFT * (xs[-1] - xs[0]))])
        self.wait(max(0.1, total - self.renderer.time))
