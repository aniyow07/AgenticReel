"""A spotlight search: the words of an idea float in the dark while a beam of light roams over them, lighting
each word it passes, until it settles on the key one, which grows to the centre as the others drift away."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, Cutout, FadeIn, FadeOut, Flash, Rectangle, Scene, ValueTracker, VGroup,  # noqa: E402
                   Write, always_redraw, config, rate_functions)

from _common import (DOWN, ambient, clean, colors, fit_width, heading, label, load_params, look_of,  # noqa: E402
                     scene_seconds)


class SpotlightScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 7.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        words = []
        for x in p.get("words") or []:
            w = clean(x)[:24]
            if w and w.lower() not in (v.lower() for v in words):
                words.append(w)
        words = words[:8]
        if len(words) < 3:
            raise ValueError("spotlight needs at least three words")
        focus = clean(p.get("focus", ""))[:24]
        fi = next((i for i, w in enumerate(words) if w.lower() == focus.lower()), 0)
        ambient(self, C, "spotlight" + "".join(words))
        title = heading(p.get("title", ""), C, fw, look)
        top = title.get_bottom()[1] - 0.6
        rng = random.Random("".join(words))
        # scatter the words on a loose grid so they never overlap
        cols = 2 if len(words) <= 4 else 3
        rows_n = math.ceil(len(words) / cols)
        cells = [(c, r) for r in range(rows_n) for c in range(cols)]
        rng.shuffle(cells)
        cw, ch = fw * 0.86 / cols, (top - (-fh / 2 + 1.4)) / rows_n
        mobs = VGroup()
        for i, w in enumerate(words):
            c, r = cells[i]
            t = fit_width(label(w, 34, C["text"]), cw * 0.9)
            t.move_to([-fw * 0.43 + cw * (c + 0.5) + rng.uniform(-0.2, 0.2) * cw,
                       top - ch * (r + 0.5) + rng.uniform(-0.2, 0.2) * ch, 0])
            t.set_opacity(0.25)
            t.base = t.get_center().copy()
            t.ph = rng.uniform(0, 6.28)
            mobs.add(t)
        r0 = max(1.0, min(cw, ch) * 0.55)
        x, y, rad = ValueTracker(-fw), ValueTracker(top), ValueTracker(r0)
        clock = ValueTracker(0)

        def light(m):  # each word brightens as the beam passes over it, and bobs gently
            d = math.hypot(m.base[0] - x.get_value(), m.base[1] - y.get_value())
            m.set_opacity(0.25 + 0.75 * max(0.0, 1 - d / (rad.get_value() * 1.1)))
            m.move_to(m.base + [0, 0.06 * math.sin(clock.get_value() * 2 + m.ph), 0])

        dark = always_redraw(lambda: Cutout(
            Rectangle(width=fw + 1, height=fh + 1),
            Circle(radius=rad.get_value()).move_to([x.get_value(), y.get_value(), 0]),
            fill_color=C["background"] if not config.transparent else "#000000", fill_opacity=0.55, stroke_width=0))
        glow = always_redraw(lambda: Circle(radius=rad.get_value(), stroke_color=C["accent"], stroke_width=3,
                                            stroke_opacity=0.7).move_to([x.get_value(), y.get_value(), 0]))
        clock.add_updater(lambda m, dt: m.increment_value(dt))
        self.add(clock)
        self.play(Write(title), *[FadeIn(m) for m in mobs], run_time=0.6)
        for m in mobs:
            m.add_updater(light)
        self.add(dark, glow)
        self.bring_to_front(title)
        others = [i for i in range(len(words)) if i != fi]
        rng.shuffle(others)
        visits = others[:3] + [fi]
        hop = max(0.35, (total - 2.6) / len(visits))
        for i in visits:
            self.play(x.animate.set_value(mobs[i].base[0]), y.animate.set_value(mobs[i].base[1]), run_time=hop,
                      rate_func=rate_functions.ease_in_out_cubic)
        key = mobs[fi]
        key.clear_updaters()
        rest = VGroup(*[m for i, m in enumerate(mobs) if i != fi])
        for m in rest:
            m.clear_updaters()
        cap = clean(p.get("caption", ""))[:40]
        caption = fit_width(label(cap, 26, C["mutedText"], weight="NORMAL"), fw * 0.8) if cap else VGroup()
        self.play(key.animate.set_opacity(1).set_color(C["accent"]).scale(1.6).move_to([0, 0.2, 0]),
                  x.animate.set_value(0), y.animate.set_value(0.2), rad.animate.set_value(max(r0, 2.2)),
                  *[m.animate.shift((m.get_center() - [0, 0.2, 0]) * 0.6).set_opacity(0) for m in rest],
                  run_time=0.8)
        self.remove(rest)
        if cap:
            caption.next_to(key, DOWN, buff=0.45)
            self.play(FadeIn(caption, shift=DOWN * 0.2), Flash(key, color=C["accent"],
                      flash_radius=key.width / 2 + 0.2, num_lines=14), run_time=0.5)
        else:
            self.play(Flash(key, color=C["accent"], flash_radius=key.width / 2 + 0.2, num_lines=14), run_time=0.5)
        self.play(FadeOut(dark), run_time=max(0.1, total - self.renderer.time))
