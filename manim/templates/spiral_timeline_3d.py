"""3D spiral timeline: events sit on a helix that climbs through space. The helix draws itself, a glowing
marker travels up it, each event's marker pops and its label appears as it is reached, and the spiral sinks
so the newest event stays in view while the camera circles."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, Create, Dot, ManimColor, ParametricFunction, Text, ThreeDScene,  # noqa: E402
                   ValueTracker, VGroup, interpolate_color, rate_functions)

from _common import FONT, clean, colors, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


class SpiralTimeline3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        events = [clean(x)[:24] for x in p.get("events", []) if str(x).strip()][:6]
        if len(events) < 2:
            raise ValueError("spiral_timeline_3d needs at least two events")
        n = len(events)
        R, rise = 1.7, 1.15  # radius, and height gained per event
        turns_per = 0.42  # fraction of a turn between events
        self.set_camera_orientation(phi=70 * DEGREES, theta=-80 * DEGREES, zoom=min(0.95, fw / 6.8))
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        lo, hi = ManimColor(C["primary"]), ManimColor(C["accent"])
        span = (n - 1) * 1.0 + 0.6

        def at(u):  # u counts events along the helix: event i sits at u = i
            a = -math.pi / 2 + u * turns_per * 2 * math.pi
            return [R * math.cos(a), R * math.sin(a), u * rise]

        helix = ParametricFunction(at, t_range=[-0.3, span], stroke_color=C["mutedText"], stroke_width=3,
                                   stroke_opacity=0.6)
        marks, tags = [], []
        for i, name in enumerate(events):
            col = interpolate_color(lo, hi, i / max(1, n - 1))
            d = Dot(at(i), radius=0.14, color=col)
            marks.append(d)
            t = Text(name, font=FONT, font_size=28, color=C["text"], weight="BOLD")
            if t.width > 2.6:
                t.scale_to_fit_width(2.6)
            x, y, z = at(i)
            k = 1 + 0.55 * 1.0 / R
            t.move_to([x * k + (0.9 if x >= 0 else -0.9), y * k, z + 0.35])
            tags.append(t)
        self.add_fixed_orientation_mobjects(*marks, *tags)
        for m in marks + tags:
            m.set_opacity(0)
        world = VGroup(helix, *marks, *tags)
        world.shift(-OUT * 0.3)
        prog = ValueTracker(-0.3)
        base = world.get_z()
        runner = Dot(radius=0.12, color=C["accent"])
        glow = Dot(radius=0.26, color=C["accent"], fill_opacity=0.3)
        self.add_fixed_orientation_mobjects(runner, glow)

        def ride(m):
            x, y, z = at(prog.get_value())
            m.move_to([x, y, z + world.get_z() - base - 0.3])
        runner.add_updater(ride)
        glow.add_updater(lambda m: m.move_to(runner))

        self.play(*show(title), Create(helix), run_time=0.8)
        self.add(runner, glow)
        self.play(*show(*notes), run_time=0.3)
        self.begin_ambient_camera_rotation(rate=0.14)
        each = max(0.35, (total - 1.9) / n)  # a little slack: each play rounds up to whole frames
        for i in range(n):
            sink = -OUT * rise if i >= 1 else -OUT * 0  # keep the newest events in the middle of the frame
            self.play(prog.animate.set_value(i), world.animate.shift(sink), run_time=each * 0.6,
                      rate_func=rate_functions.ease_in_out_sine)
            self.play(marks[i].animate.set_opacity(1).scale(1.3), tags[i].animate.set_opacity(1),
                      run_time=each * 0.4)
        self.wait(max(0.1, total - self.renderer.time))
