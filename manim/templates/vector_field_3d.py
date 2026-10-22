"""3D vector field: a block of arrows for a named field shape grows in, a test particle follows the field
leaving a glowing trail, and the camera orbits quickly with a rising tilt. No AI-written formulas."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, Create, Dot, Dot3D, Line, FadeIn, LaggedStart, ManimColor, ThreeDScene,  # noqa: E402
                   TracedPath, VGroup, interpolate_color)

from _common import colors, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


def _norm(v):
    return math.sqrt(sum(c * c for c in v))


def _dipole(x, y, z):
    out = [0.0, 0.0, 0.0]
    for q, cx in ((1, 1.2), (-1, -1.2)):
        d = [x - cx, y, z]
        r = max(_norm(d), 0.35)
        out = [o + q * c / r ** 3 for o, c in zip(out, d)]
    return out


FIELDS = {
    "source": lambda x, y, z: [x, y, z],
    "sink": lambda x, y, z: [-x, -y, -z],
    "vortex": lambda x, y, z: [-y, x, 0.0],
    "uniform": lambda x, y, z: [1.0, 0.25, 0.15],
    "dipole": _dipole,
    "helix": lambda x, y, z: [-y, x, 0.7],
}
START = {"source": [0.25, 0.15, 0.1], "sink": [2.3, 1.8, 1.4], "vortex": [1.6, 0, -0.8], "uniform": [-2.4, -1, -0.6],
         "dipole": [1.35, 0.25, 0.2], "helix": [1.4, 0, -1.6]}


class VectorField3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        kind = p.get("field") if p.get("field") in FIELDS else "source"
        F = FIELDS[kind]
        self.set_camera_orientation(phi=60 * DEGREES, theta=-45 * DEGREES, zoom=min(0.85, fw / 8.5))
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])

        lo, hi = ManimColor(C["primary"]), ManimColor(C["accent"])
        arrows = VGroup()
        pts = [(x, y, z) for x in (-2, -0.7, 0.7, 2) for y in (-2, -0.7, 0.7, 2) for z in (-1.2, 0, 1.2)]
        mags = [_norm(F(*q)) for q in pts]
        top = max(mags) or 1
        for q, m in zip(pts, mags):
            if m < 1e-6:
                continue
            d = [c / m * 0.7 for c in F(*q)]
            col = interpolate_color(lo, hi, min(1.0, (m / top) ** 0.5))
            # a line fading in from its tail and a bright head that always faces the camera (cheap to render)
            shaft = Line([q[i] - d[i] / 2 for i in range(3)], [q[i] + d[i] / 2 for i in range(3)], stroke_width=6)
            shaft.set_stroke(col, width=6, opacity=0.85)
            arrows.add(VGroup(shaft, Dot(shaft.get_end(), radius=0.075, color=col)))

        # the charges that make the field, where it has them (+ warm, - cool)
        charges = VGroup(*[Dot(at, radius=0.2, color=c) for at, c in
                           {"source": [([0, 0, 0], C["accent"])], "sink": [([0, 0, 0], C["primary"])],
                            "dipole": [([1.2, 0, 0], C["accent"]), ([-1.2, 0, 0], C["primary"])]}.get(kind, [])])
        self.add_fixed_orientation_mobjects(*[a[1] for a in arrows], *charges)
        self.add(charges)
        self.play(*show(title), LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.01), run_time=1.2)
        probe = Dot3D(START[kind], radius=0.1, color=C["text"])
        trail = TracedPath(probe.get_center, stroke_color=C["accent"], stroke_width=4, dissipating_time=1.5)

        def follow(m, dt):
            pos = list(m.get_center())
            v = F(*pos)
            n = _norm(v) or 1
            nxt = [a + c / n * 1.3 * dt for a, c in zip(pos, v)]
            if max(abs(c) for c in nxt) > 2.8 or (kind == "sink" and _norm(nxt) < 0.2) or \
                    (kind == "dipole" and _norm([nxt[0] + 1.2, nxt[1], nxt[2]]) < 0.25):
                nxt = START[kind]
            m.move_to(nxt)
        self.add(trail)
        self.play(FadeIn(probe), *show(*notes), run_time=0.4)
        probe.add_updater(follow)
        self.begin_ambient_camera_rotation(rate=0.35)
        self.move_camera(phi=75 * DEGREES, run_time=max(0.5, total - self.renderer.time - 0.2))
        self.wait(max(0.1, total - self.renderer.time))
