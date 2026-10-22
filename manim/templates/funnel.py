"""A funnel of narrowing stages (sales funnels, hiring, filtering, natural selection): the stages stack
from widest to narrowest, then a stream of particles pours in at the top and fewer make it through each
stage, the rest flicking away to the sides. Optional values (from the sources) are shown beside each stage."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Dot, FadeIn, Flash, Polygon, Scene, Text, VGroup, Write)  # noqa: E402

from _common import (FONT, LEFT, RIGHT, ambient, clean, colors, fit_width, heading, label, load_params,  # noqa: E402
                     look_of, mix, num_text, scene_seconds)


class FunnelScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        stages = [clean(x)[:32] for x in p.get("stages") or [] if str(x).strip()][:5]
        if len(stages) < 2:
            raise ValueError("funnel needs at least two stages")
        raw = p.get("values") or []
        values = [float(v) for v in raw] if len(raw) == len(stages) else []
        unit = str(p.get("unit") or "")[:12]
        n = len(stages)
        ambient(self, C, "funnel" + "".join(stages))
        title = heading(p.get("title", ""), C, fw, look)
        top = title.get_bottom()[1] - 0.4
        bottom = -fh / 2 + 0.55
        h = (top - bottom) / n
        cx = -fw * 0.08 if values else 0
        w_top, w_bot = fw * (0.7 if values else 0.84), fw * 0.16

        def half(y):  # half the funnel's width at height y
            return (w_bot + (w_top - w_bot) * (y - bottom) / (top - bottom)) / 2

        gap = 0.06 if look != "underline" else 0
        layers, notes = [], []
        for i, name in enumerate(stages):
            y1, y0 = top - i * h, top - (i + 1) * h + gap
            col = mix(C["primary"], C["accent"], i / max(1, n - 1))
            shape = Polygon([cx - half(y1), y1, 0], [cx + half(y1), y1, 0], [cx + half(y0), y0, 0],
                            [cx - half(y0), y0, 0], stroke_width=0 if look in ("pill", "sharp") else 2.5,
                            stroke_color=C["text"], fill_color=col, fill_opacity=0.8 if look != "glass" else 0.3)
            t = fit_width(label(name, 26, C["text"] if look == "glass" else C["background"]), half(y0) * 1.7)
            t.move_to([cx, (y0 + y1) / 2, 0])
            layers.append(VGroup(shape, t))
            if values:
                v = Text(num_text(values[i], raw[i]) + unit, font=FONT, font_size=26, color=col, weight="BOLD")
                fit_width(v, fw / 2 - (cx + half(y1)) - 0.3)
                v.next_to([cx + half((y0 + y1) / 2), (y0 + y1) / 2, 0], RIGHT, buff=0.3)
                notes.append(v)

        # how many particles survive each stage: from the values if there are any, otherwise a steady taper
        if values and values[0] > 0:
            keep = [max(0.0, min(1.0, v / values[0])) for v in values]
        else:
            keep = [1 - 0.75 * i / max(1, n - 1) for i in range(n)]
        rng = random.Random("".join(stages))
        dots = VGroup()
        flow = max(1.0, total - 0.6 - 0.35 * n)
        for k in range(46):
            d = Dot(radius=0.06, color=C["text"], fill_opacity=0)
            d.u = rng.uniform(-0.85, 0.85)
            d.delay = rng.uniform(0, flow * 0.8)
            d.t = 0.0
            r = rng.random()
            d.depth = sum(1 for q in keep[1:] if r < q)  # number of stages this particle gets through
            d.speed = (top - bottom) / rng.uniform(1.4, 2.0)
            d.kick = rng.choice((-1, 1)) * rng.uniform(1.5, 3)

            def fall(m, dt):
                m.t += dt
                age = m.t - m.delay
                if age < 0:
                    return
                y = top + 0.3 - age * m.speed
                stop = top - (m.depth + 1) * h + 0.15
                if y > stop or m.depth == n - 1:
                    m.move_to([cx + m.u * half(max(bottom, y)) * (1 if y > bottom else 0.4), max(bottom - 1.2, y), 0])
                    m.set_opacity(1 if y > bottom - 0.6 else 0)
                else:  # filtered out: flick sideways and fade
                    off = (stop - y)
                    m.move_to([cx + m.u * half(stop) + m.kick * off, stop - off * 0.3, 0])
                    m.set_opacity(max(0.0, 1 - off * 1.5))
            d.add_updater(fall)
            dots.add(d)

        self.play(Write(title), run_time=0.5)
        for i, layer in enumerate(layers):
            self.play(FadeIn(layer, shift=(LEFT if i % 2 else RIGHT) * 0.5),
                      *([FadeIn(notes[i], shift=LEFT * 0.3)] if notes else []), run_time=0.35)
        self.add(dots)
        self.wait(max(0.2, total - self.renderer.time - 0.5))
        self.play(Flash([cx, bottom, 0], color=C["accent"], flash_radius=0.5, num_lines=12), run_time=0.45)
