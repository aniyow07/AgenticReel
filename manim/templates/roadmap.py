"""A journey or plan as a winding road: the road unrolls up the screen, a glowing marker drives along it
leaving a trail, a flag pops up at each stop as the marker reaches it, and the goal is crowned at the top."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from manim import (Create, DashedVMobject, Dot, FadeIn, Flash, Line, Polygon, Scene, Star, TracedPath,  # noqa: E402
                   ValueTracker, VGroup, VMobject, Write, rate_functions)

from _common import (DOWN, LEFT, RIGHT, UP, ambient, card, clean, colors, fit_width, heading, label,  # noqa: E402
                     load_params, look_of, mix, scene_seconds, wrap)


class RoadmapScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        stops = [clean(x)[:40] for x in p.get("stops") or [] if str(x).strip()][:6]
        if len(stops) < 2:
            raise ValueError("roadmap needs at least two stops")
        goal = clean(p.get("goal", ""))[:30]
        n = len(stops)
        ambient(self, C, "roadmap" + "".join(stops))
        title = heading(p.get("title", ""), C, fw, look)
        top = title.get_bottom()[1] - (1.0 if goal else 0.5)
        bottom = -fh / 2 + 0.5
        amp = fw * 0.13
        apex = [np.array([(-amp if i % 2 == 0 else amp), bottom + (top - bottom) * (i + 0.6) / (n + 0.2), 0])
                for i in range(n)]
        pts = [np.array([0, bottom - 0.2, 0])] + apex + [np.array([0, top + 0.15, 0])]
        road_path = VMobject().set_points_smoothly(pts)
        road = road_path.copy().set_stroke(C["surface"] if look != "glass" else C["text"], 30,
                                           opacity=1 if look != "glass" else 0.12)
        edge = road_path.copy().set_stroke(C["primary"], 36, opacity=0.35)
        centre = DashedVMobject(road_path.copy().set_stroke(C["text"], 3, opacity=0.8), num_dashes=40)
        samples = [road_path.point_from_proportion(k / 400) for k in range(401)]
        where = [min(range(401), key=lambda k: np.linalg.norm(samples[k] - a)) / 400 for a in apex]

        flags = []
        for i, (a, text) in enumerate(zip(apex, stops)):
            side = LEFT if a[0] < 0 else RIGHT
            col = mix(C["primary"], C["accent"], i / max(1, n - 1))
            pole = Line(a, a + UP * 0.55, color=C["text"], stroke_width=3)
            cloth = Polygon(a + UP * 0.55, a + UP * 0.33, a + UP * 0.44 + side * 0.38, stroke_width=0,
                            fill_color=col, fill_opacity=1)
            room = fw / 2 - abs(a[0]) - 0.65
            tag = card(wrap(text, 16, 2), C, room, look, col, size=22, min_h=0.6)
            tag.next_to(a, side, buff=0.5)
            flags.append((VGroup(pole, cloth), tag, Dot(a, radius=0.11, color=col)))
        end = None
        if goal:
            end = VGroup(Star(n=5, outer_radius=0.26, fill_color=C["accent"], fill_opacity=1, stroke_width=0),
                         fit_width(label(goal, 28, C["accent"]), fw * 0.7)).arrange(RIGHT, buff=0.2)
            end.next_to(road_path.get_end(), UP, buff=0.12)

        prog = ValueTracker(0)
        car = Dot(road_path.get_start(), radius=0.15, color=C["accent"])
        car.add_updater(lambda m: m.move_to(road_path.point_from_proportion(max(0, min(1, prog.get_value())))))
        halo = Dot(radius=0.3, color=C["accent"], fill_opacity=0.25).add_updater(lambda m: m.move_to(car))
        trail = TracedPath(car.get_center, stroke_color=C["accent"], stroke_width=6, stroke_opacity=0.8)

        self.play(Write(title), run_time=0.5)
        self.play(Create(edge), Create(road), run_time=0.7)
        self.play(Create(centre), run_time=0.3)
        self.add(trail, halo, car)
        legs = where + [1.0]
        each = max(0.3, (total - 2.6) / (n + 1))
        for i, stop_at in enumerate(legs):
            self.play(prog.animate.set_value(stop_at), run_time=each * 0.6, rate_func=rate_functions.ease_in_out_sine)
            if i < n:
                flag, tag, dot = flags[i]
                self.play(FadeIn(dot, scale=2), FadeIn(flag, shift=UP * 0.3), FadeIn(tag, shift=DOWN * 0.2),
                          Flash(dot, color=C["accent"], line_length=0.15, flash_radius=0.25), run_time=each * 0.4)
        if end:
            self.play(FadeIn(end, shift=DOWN * 0.3, scale=0.6), run_time=0.35)
            self.play(Flash(end[0], color=C["accent"], num_lines=14, flash_radius=0.45), run_time=0.35)
        self.wait(max(0.1, total - self.renderer.time))
