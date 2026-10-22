"""3D crystal: the camera starts deep inside a named lattice and pulls back while swinging round, then one
unit cell lights up. Atom positions are built in."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import DEGREES, Create, Dot, FadeIn, Line, ThreeDScene, VGroup  # noqa: E402

from _common import colors, legend, load_params, look_of, overlay, scene_seconds, show  # noqa: E402

NAMES = {"simple_cubic": "Simple cubic", "body_centered": "Body-centred cubic",
         "face_centered": "Face-centred cubic", "salt": "Rock salt"}


def _sites(kind: str, n: int = 2):
    """(position in cell units, species 0/1) for an n x n x n block of cells."""
    if kind == "salt":
        return [((i / 2, j / 2, k / 2), (i + j + k) % 2) for i, j, k in itertools.product(range(2 * n + 1), repeat=3)]
    out = [((i, j, k), 0) for i, j, k in itertools.product(range(n + 1), repeat=3)]
    if kind == "body_centered":
        out += [((i + .5, j + .5, k + .5), 1) for i, j, k in itertools.product(range(n), repeat=3)]
    if kind == "face_centered":
        for i, j, k in itertools.product(range(n + 1), repeat=3):
            for a, b, c in ((.5, .5, 0), (.5, 0, .5), (0, .5, .5)):
                q = (i + a, j + b, k + c)
                if max(q) <= n:
                    out.append((q, 1))
    return out


class CrystalLattice3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        kind = p.get("lattice") if p.get("lattice") in NAMES else "simple_cubic"
        a, n = 1.5, 2
        off = a * n / 2
        cols = [C["primary"], C["accent"]]
        radius = (0.2, 0.13) if kind == "salt" else (0.17, 0.14)

        base_zoom = min(0.85, fw / 7.5)
        self.set_camera_orientation(phi=72 * DEGREES, theta=-20 * DEGREES, zoom=base_zoom * 2.6)
        title, *_ = overlay(self, p, C, look)
        key = legend([NAMES[kind]] if kind != "salt" else ["Sodium", "Chloride"], cols, C, fw,
                     head=str(p.get("caption", ""))[:40])
        self.add_fixed_in_frame_mobjects(key)
        key.set_opacity(0)

        # flat discs that always face the camera, with a highlight: they read as balls and render fast
        atoms = VGroup()
        for q, s in _sites(kind, n):
            at = [c * a - off for c in q]
            ball = VGroup(Dot(at, radius=radius[s], color=cols[s]),
                          Dot(at, radius=radius[s] * 0.4, color=C["text"], fill_opacity=0.55)
                          .shift([-radius[s] * 0.3, 0, radius[s] * 0.3]))
            atoms.add(ball)
        step = a / 2 if kind == "salt" else a
        m = int(round(a * n / step))
        bonds = VGroup()
        for i, j, k in itertools.product(range(m + 1), repeat=3):
            p0 = [i * step - off, j * step - off, k * step - off]
            for d in range(3):
                if (i, j, k)[d] < m:
                    p1 = list(p0)
                    p1[d] += step
                    bonds.add(Line(p0, p1, stroke_width=1.5, stroke_color=C["mutedText"], stroke_opacity=0.5))
        cell = VGroup()
        for i, j, k in itertools.product(range(2), repeat=3):
            p0 = [i * a - off, j * a - off, k * a - off]
            for d in range(3):
                if (i, j, k)[d] == 0:
                    p1 = list(p0)
                    p1[d] += a
                    cell.add(Line(p0, p1, stroke_width=5, stroke_color=C["accent"]))

        self.add_fixed_orientation_mobjects(*[b for b in atoms])
        self.play(*show(title), FadeIn(atoms), Create(bonds), run_time=0.8)
        pull = max(1.2, (total - self.renderer.time) * 0.6)
        self.move_camera(zoom=base_zoom, theta=-55 * DEGREES, phi=65 * DEGREES, added_anims=show(key), run_time=pull)
        self.begin_ambient_camera_rotation(rate=0.15)
        self.play(Create(cell), run_time=0.6)
        self.wait(max(0.2, total - self.renderer.time))
