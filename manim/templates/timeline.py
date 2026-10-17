"""Vertical timeline: the line draws itself, a glowing marker travels down it, and each
event pops in and is highlighted as the marker passes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Create, Dot, FadeIn, Flash, Line, Scene, VGroup, Write)  # noqa: E402

from _common import (DOWN, LEFT, RIGHT, UP, ambient, colors, fit_width, label, load_params,  # noqa: E402
                     scene_seconds)


class TimelineScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        events = [e for e in p.get("events", []) if isinstance(e, dict) and str(e.get("label", "")).strip()][:6]
        if len(events) < 2:
            raise ValueError("timeline needs at least two events")
        total = scene_seconds(p, 6.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "timeline" + str(events[0]["label"]))

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        top = title.get_bottom()[1] - 0.5
        bottom_y = -fh / 2 + 0.5
        x = -fw * 0.36
        spacing = (top - bottom_y) / len(events)
        line = Line([x, top, 0], [x, bottom_y, 0], color=C["primary"], stroke_width=6)
        marker = Dot([x, top, 0], radius=0.16, color=C["accent"])
        halo = Dot([x, top, 0], radius=0.32, color=C["accent"], fill_opacity=0.25)
        halo.add_updater(lambda m: m.move_to(marker))

        items = []
        for i, ev in enumerate(events):
            y = top - spacing * (i + 0.5)
            dot = Dot([x, y, 0], radius=0.12, color=C["primary"])
            head = fit_width(label(ev["label"], 30, C["text"]), fw * 0.66)
            group = VGroup(head)
            if str(ev.get("detail", "")).strip():
                det = fit_width(label(ev["detail"], 22, C["mutedText"], weight="NORMAL"), fw * 0.66)
                group.add(det)
                group.arrange(DOWN, aligned_edge=LEFT, buff=0.08)
            group.next_to(dot, RIGHT, buff=0.35)
            items.append((dot, group, y))

        each = (total - 1.4) / len(events)
        self.play(Write(title), run_time=0.6)
        self.play(Create(line), FadeIn(marker), FadeIn(halo), run_time=0.6)
        for dot, group, y in items:
            self.play(marker.animate.move_to([x, y, 0]), run_time=each * 0.35)
            self.play(FadeIn(dot, scale=2.2), FadeIn(group, shift=LEFT * 0.3),
                      Flash(dot, color=C["accent"], line_length=0.2, flash_radius=0.25), run_time=each * 0.45)
            self.play(dot.animate.set_color(C["accent"]), group[0].animate.set_color(C["accent"]),
                      run_time=each * 0.2)
            group[0].set_color(C["text"])
        self.wait(0.2)
