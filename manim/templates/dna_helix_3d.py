"""3D DNA: two strands spiral into place, base-pair rungs snap across, and the camera climbs the slowly
turning double helix from bottom to top."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, Create, Dot, Line, ParametricFunction, ThreeDScene, VGroup,  # noqa: E402
                   LaggedStart)

from _common import SERIES, colors, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


class DNAHelix3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        self.set_camera_orientation(phi=80 * DEGREES, theta=-30 * DEGREES, zoom=min(0.7, fw / 11.4),
                                    frame_center=[0, 0, -0.9])

        r, rise, turns = 1.0, 0.55, 2.0
        t_max = turns * 2 * math.pi
        z0 = -rise * t_max / 2

        def strand(phase):
            return ParametricFunction(lambda t: [r * math.cos(t + phase), r * math.sin(t + phase), z0 + rise * t],
                                      t_range=[0, t_max], stroke_width=6)
        a = strand(0).set_color(C["primary"])
        b = strand(2.4).set_color(C["accent"])
        pairs = [SERIES[0], SERIES[1], SERIES[2], C["text"]]
        rungs, beads = VGroup(), VGroup()
        for k in range(int(turns * 10)):
            t = (k + 0.5) * t_max / (turns * 10)
            p1 = [r * math.cos(t), r * math.sin(t), z0 + rise * t]
            p2 = [r * math.cos(t + 2.4), r * math.sin(t + 2.4), z0 + rise * t]
            mid = [(x + y) / 2 for x, y in zip(p1, p2)]
            col = pairs[(k * 7) % 4]
            rungs.add(Line(p1, mid, stroke_width=5, color=col), Line(mid, p2, stroke_width=5,
                                                                      color=pairs[(k * 7 + 2) % 4]))
            beads.add(Dot(p1, radius=0.08, color=C["primary"]), Dot(p2, radius=0.08, color=C["accent"]))
        helix = VGroup(a, b, rungs, beads)

        self.play(*show(title), Create(a), Create(b), run_time=1.2)
        self.play(LaggedStart(*[Create(x) for x in rungs], lag_ratio=0.03), *show(*notes), run_time=1.0)
        self.add(beads)
        helix.add_updater(lambda m, dt: m.rotate(0.45 * dt, axis=OUT, about_point=[0, 0, 0]))
        climb = max(1.0, total - self.renderer.time - 0.3)
        self.move_camera(phi=62 * DEGREES, frame_center=[0, 0, 0.9], run_time=climb)
        self.wait(max(0.1, total - self.renderer.time))
