"""Pyramid / hierarchy: layers stack from the base up (Maslow, food chains, the OSI model, priorities),
widest at the bottom; each layer slides in with its label and the top one is crowned with a flash."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (FadeIn, Flash, Indicate, Polygon, Scene, VGroup, Write)  # noqa: E402

from _common import (LEFT, RIGHT, ambient, colors, fit_width, heading, label, load_params, look_of,  # noqa: E402
                     scene_seconds)


def mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


class PyramidScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        levels = [s for s in p.get("levels", []) if str(s).strip()][:6]  # top first
        if len(levels) < 2:
            raise ValueError("pyramid needs at least two levels")
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "pyramid" + "".join(levels))
        title = heading(p.get("title", ""), C, fw, look)
        n = len(levels)
        top_y = title.get_bottom()[1] - 0.95  # room for the apex label
        bottom_y = -fh / 2 + 0.7
        h = (top_y - bottom_y) / n
        base_w = fw * 0.9
        gap = 0.08 if look != "underline" else 0.0
        layers = []
        for i in range(n):  # i = 0 is the top
            y1 = top_y - i * h
            y0 = y1 - h + gap
            w1 = base_w * i / n
            w0 = base_w * (i + 1) / n
            shape = Polygon([-w0 / 2, y0, 0], [w0 / 2, y0, 0], [w1 / 2, y1, 0], [-w1 / 2, y1, 0],
                            stroke_width=0 if look in ("pill", "sharp") else 3, stroke_color=C["text"],
                            fill_color=mix(C["accent"], C["primary"], i / max(1, n - 1)),
                            fill_opacity=0.85 if look != "glass" else 0.35)
            if i == 0:  # the apex is too narrow for words: label it just above the tip
                t = fit_width(label(levels[i], 26, C["accent"]), fw * 0.8)
                t.move_to([0, y1 + 0.3, 0])
            else:
                t = fit_width(label(levels[i], 26, C["text"] if look == "glass" else C["background"]),
                              max(0.6, (w0 + w1) / 2 * 0.78))
                t.move_to([0, (y0 + y1) / 2, 0])
            layers.append(VGroup(shape, t))
        self.play(Write(title), run_time=0.6)
        build = max(1.0, (total - 1.6) * 0.65)
        for k, layer in enumerate(reversed(layers)):
            self.play(FadeIn(layer, shift=(RIGHT if k % 2 else LEFT) * 0.6), run_time=build / n)
        self.play(Flash(layers[0][0].get_top(), color=C["accent"], num_lines=12, flash_radius=0.6), run_time=0.5)
        rest = max(0.3, total - self.renderer.time)
        self.play(*[Indicate(l[0], color=C["accent"], scale_factor=1.03) for l in layers[:1]], run_time=rest)
