"""3D molecule: a ball-and-stick model of a named molecule (fixed coordinates, no AI input) builds atom by
atom, tumbles in space, and the camera punches in. Element names sit in a fixed key."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, GrowFromCenter, LaggedStart, Line3D, Sphere, ThreeDScene, VGroup, Create)  # noqa: E402

from _common import colors, legend, load_params, look_of, overlay, scene_seconds, show  # noqa: E402

ELEMENTS = {"H": ("Hydrogen", "#F2F4F8", 0.22), "C": ("Carbon", "#8A93A6", 0.34), "O": ("Oxygen", "#FF5A5F", 0.33),
            "N": ("Nitrogen", "#4C8DFF", 0.33)}


def _ring(n, r, z=0.0, off=0.0):
    return [(r * math.cos(off + 2 * math.pi * i / n), r * math.sin(off + 2 * math.pi * i / n), z) for i in range(n)]


def _benzene():
    cs, hs = _ring(6, 1.39), _ring(6, 2.48)
    atoms = [("C", c) for c in cs] + [("H", h) for h in hs]
    bonds = [(i, (i + 1) % 6, 2 if i % 2 == 0 else 1) for i in range(6)] + [(i, i + 6, 1) for i in range(6)]
    return atoms, bonds


_T = 0.63
MOLECULES = {
    "water": ([("O", (0, -0.2, 0)), ("H", (0.76, 0.39, 0)), ("H", (-0.76, 0.39, 0))], [(0, 1, 1), (0, 2, 1)]),
    "carbon_dioxide": ([("C", (0, 0, 0)), ("O", (1.16, 0, 0)), ("O", (-1.16, 0, 0))], [(0, 1, 2), (0, 2, 2)]),
    "methane": ([("C", (0, 0, 0)), ("H", (_T, _T, _T)), ("H", (_T, -_T, -_T)), ("H", (-_T, _T, -_T)),
                 ("H", (-_T, -_T, _T))], [(0, i, 1) for i in range(1, 5)]),
    "ammonia": ([("N", (0, 0, 0.12)), ("H", (0.94, 0, -0.27)), ("H", (-0.47, 0.81, -0.27)),
                 ("H", (-0.47, -0.81, -0.27))], [(0, i, 1) for i in range(1, 4)]),
    "ethylene": ([("C", (0.67, 0, 0)), ("C", (-0.67, 0, 0)), ("H", (1.23, 0.92, 0)), ("H", (1.23, -0.92, 0)),
                  ("H", (-1.23, 0.92, 0)), ("H", (-1.23, -0.92, 0))],
                 [(0, 1, 2), (0, 2, 1), (0, 3, 1), (1, 4, 1), (1, 5, 1)]),
    "benzene": _benzene(),
    "oxygen": ([("O", (0.6, 0, 0)), ("O", (-0.6, 0, 0))], [(0, 1, 2)]),
    "ethanol": ([("C", (-1.17, -0.4, 0)), ("C", (0.2, 0.25, 0)), ("O", (1.2, -0.75, 0)), ("H", (2.05, -0.3, 0)),
                 ("H", (-1.9, 0.4, 0)), ("H", (-1.3, -1.02, 0.89)), ("H", (-1.3, -1.02, -0.89)),
                 ("H", (0.33, 0.88, 0.89)), ("H", (0.33, 0.88, -0.89))],
                [(0, 1, 1), (1, 2, 1), (2, 3, 1), (0, 4, 1), (0, 5, 1), (0, 6, 1), (1, 7, 1), (1, 8, 1)]),
}


class Molecule3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        atoms, bonds = MOLECULES.get(str(p.get("molecule")), MOLECULES["water"])
        span = max(max(abs(c) for c in xyz) for _, xyz in atoms) * 2 + 1.2
        scale = min(1.6, 4.2 / span)
        pts = [[c * scale for c in xyz] for _, xyz in atoms]
        self.set_camera_orientation(phi=70 * DEGREES, theta=-40 * DEGREES, zoom=min(1.0, fw / 7))
        title, *notes = overlay(self, p, C, look)
        els = list(dict.fromkeys(e for e, _ in atoms))
        key = legend([ELEMENTS[e][0] for e in els], [ELEMENTS[e][1] for e in els], C, fw,
                     head=str(p.get("caption", ""))[:40])
        self.add_fixed_in_frame_mobjects(key)
        key.set_opacity(0)

        balls = VGroup(*[Sphere(center=pt, radius=ELEMENTS[e][2] * scale ** 0.5, resolution=(10, 10))
                         .set_color(ELEMENTS[e][1]) for (e, _), pt in zip(atoms, pts)])
        sticks = VGroup()
        for i, j, order in bonds:
            a, b = pts[i], pts[j]
            d = [b[k] - a[k] for k in range(3)]
            n = [-d[1], d[0], 0] if abs(d[2]) < 0.9 * math.sqrt(sum(x * x for x in d)) else [1, 0, 0]
            L = math.sqrt(sum(x * x for x in n)) or 1
            offs = [0.0] if order == 1 else [-0.09, 0.09]
            for o in offs:
                sh = [n[k] / L * o for k in range(3)]
                sticks.add(Line3D([a[k] + sh[k] for k in range(3)], [b[k] + sh[k] for k in range(3)],
                                  thickness=0.035, color=C["mutedText"], resolution=6))
        mol = VGroup(sticks, balls)

        self.play(*show(title), LaggedStart(*[GrowFromCenter(b) for b in balls], lag_ratio=0.15), run_time=1.2)
        self.play(*[Create(s) for s in sticks], *show(key), run_time=0.7)
        mol.add_updater(lambda m, dt: m.rotate(0.7 * dt, axis=[0.3, 1, 0.6], about_point=[0, 0, 0]))
        rest = max(0.6, total - self.renderer.time - 0.2)
        self.move_camera(zoom=min(1.0, fw / 7) * 1.25, theta=-10 * DEGREES, run_time=rest)
        self.wait(max(0.1, total - self.renderer.time))
