"""One big number from the sources, revealed with impact. "counter": the digits race up to the value inside
a burst of rays. "ring": a percentage fills a ring around the counter. "dots": a 10 x 10 grid of dots lights
up one by one until the percentage is reached. Ring and dots need a value of 0-100 with a "%" suffix; any
other value is shown as a counter."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (TAU, AnimationGroup, Arc, Circle, Dot, FadeIn, Flash, Line, Scene, Text, ValueTracker, VGroup,  # noqa: E402
                   Write, rate_functions)

from _common import (DOWN, FONT, UP, ambient, clean, colors, fit_width, heading, label, load_params,  # noqa: E402
                     look_of, num_text, scene_seconds, wrap)


class StatRevealScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 6.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        value = float(p.get("value", 0))
        # a leading space in the suffix (" tonnes") must survive, so it becomes a no-break space
        prefix, suffix = (" ".join(str(p.get(k) or "").split("\n")).replace(" ", " ")[:n]
                          for k, n in (("prefix", 6), ("suffix", 12)))
        style = p.get("style") if p.get("style") in ("counter", "ring", "dots") else "counter"
        if style != "counter" and not (suffix.strip() == "%" and 0 <= value <= 100):
            style = "counter"
        ambient(self, C, "stat" + str(value))
        title = heading(p.get("title", ""), C, fw, look)
        cap = clean(p.get("label", ""))
        caption = fit_width(label(wrap(cap, 28, 2), 28, C["text"], weight="NORMAL"), fw * 0.86) if cap else VGroup()
        tracker = ValueTracker(0)
        big = 96 if style == "counter" else 64

        def number():
            t = Text(f"{prefix}{num_text(tracker.get_value(), p.get('value'))}{suffix}", font=FONT, font_size=big,
                     color=C["accent"], weight="BOLD")
            return fit_width(t, fw * (0.84 if style == "counter" else 0.5))

        centre = [0, 0.2 if style != "dots" else 0, 0]
        num = number().move_to(centre)
        num.add_updater(lambda m: m.become(number().move_to(centre)))
        grow = max(1.2, (total - 1.6) * 0.6)
        self.play(Write(title), run_time=0.5)
        self.add(num)
        if style == "counter":
            caption.next_to(num, DOWN, buff=0.5)
            rays = VGroup(*[Line(UP * 1.6, UP * 2.6, color=C["primary"], stroke_width=4, stroke_opacity=0.6)
                            .rotate(k * TAU / 16, about_point=[0, 0, 0]) for k in range(16)]).move_to(centre)
            rays.add_updater(lambda m, dt: m.rotate(0.35 * dt))
            self.play(FadeIn(rays, scale=0.4), tracker.animate.set_value(value), run_time=grow,
                      rate_func=rate_functions.ease_out_cubic)
            self.play(Flash(num, color=C["accent"], flash_radius=num.width / 2 + 0.3, num_lines=18),
                      FadeIn(caption, shift=UP * 0.3), run_time=0.6)
        elif style == "ring":
            r = 2.0
            track = Circle(radius=r, stroke_color=C["text"], stroke_opacity=0.15, stroke_width=22).move_to(centre)
            arc = Arc(radius=r, start_angle=math.pi / 2, angle=-1e-3, stroke_color=C["accent"],
                      stroke_width=22).move_arc_center_to(centre)
            arc.add_updater(lambda m: m.become(
                Arc(radius=r, start_angle=math.pi / 2, angle=-TAU * max(1e-3, tracker.get_value()) / 100,
                    stroke_color=C["accent"], stroke_width=22).move_arc_center_to(centre)))
            caption.next_to(track, DOWN, buff=0.4)
            self.play(FadeIn(track), run_time=0.3)
            self.add(arc)
            self.play(tracker.animate.set_value(value), run_time=grow, rate_func=rate_functions.ease_out_cubic)
            arc.clear_updaters()
            self.play(Flash(arc.get_end(), color=C["accent"], num_lines=12, flash_radius=0.4),
                      FadeIn(caption, shift=UP * 0.3), run_time=0.6)
        else:
            num.clear_updaters()
            grid = VGroup(*[Dot(radius=0.11, color=C["text"], fill_opacity=0.18) for _ in range(100)])
            grid.arrange_in_grid(10, 10, buff=0.16).move_to([0, -0.15, 0])
            room = (title.get_bottom()[1] - 0.3) - (-fh / 2 + 0.4)
            stack = VGroup(num, grid, caption).arrange(DOWN, buff=0.35)
            if stack.height > room:
                stack.scale_to_fit_height(room)
            stack.move_to([0, (title.get_bottom()[1] - 0.3 + -fh / 2 + 0.4) / 2, 0])
            lit = round(value)
            self.remove(num)
            self.play(FadeIn(grid, lag_ratio=0.01), run_time=0.5)
            place, tall = num.get_center(), num.height
            num.add_updater(lambda m: m.become(number().scale_to_fit_height(tall).move_to(place)))
            self.add(num)
            on = [d.animate.set_fill(C["accent"], opacity=1).scale(1.15) for d in grid[:lit]]
            if on:
                self.play(AnimationGroup(*on, lag_ratio=0.02), tracker.animate.set_value(value), run_time=grow)
            else:
                self.play(tracker.animate.set_value(value), run_time=grow)
            self.play(FadeIn(caption, shift=UP * 0.3), run_time=0.5)
        num.clear_updaters()
        self.play(num.animate.scale(1.08), run_time=0.2)
        self.play(num.animate.scale(1 / 1.08), run_time=0.2)
        self.wait(max(0.1, total - self.renderer.time))
