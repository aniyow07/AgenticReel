"""3D nested layers: shells grow out from the core one after another, then peel away from the outside in
while the camera pushes closer, and a fixed key lights up the layer being shown (innermost listed first)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import DEGREES, GrowFromCenter, ManimColor, Sphere, ThreeDScene, interpolate_color  # noqa: E402

from _common import clean, colors, legend, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


class PlanetLayers3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:24] for x in p.get("layers", []) if str(x).strip()][:5]
        if len(names) < 2:
            raise ValueError("planet_layers_3d needs at least two layers")
        n = len(names)
        z0 = min(0.95, fw / 6.8)
        self.set_camera_orientation(phi=70 * DEGREES, theta=-50 * DEGREES, zoom=z0)
        title, *_ = overlay(self, p, C, look)
        hot, cool = ManimColor(C["accent"]), ManimColor(C["primary"])
        cols = [interpolate_color(hot, cool, i / max(1, n - 1)).to_hex() for i in range(n)]
        cap = clean(p.get("caption", ""))[:40]
        key = legend(list(reversed(names)), list(reversed(cols)), C, fw, head=cap)
        rows = list(key)[1:] if cap else list(key)  # rows[0] is the outermost layer
        self.add_fixed_in_frame_mobjects(key)
        key.set_opacity(0)

        radii = [0.55 + 1.35 * (i + 1) / n for i in range(n)]
        shells = []
        for i, r in enumerate(radii):
            s = Sphere(radius=r, resolution=(12, 18), stroke_width=0)
            s.set_fill(cols[i], opacity=0.95 if i == 0 else 0.28 + 0.12 * (n - i) / n)
            shells.append(s)

        grow = min(0.45, (total - 3) / (2 * n))
        self.play(*show(title), GrowFromCenter(shells[0]), run_time=0.6)
        for s in shells[1:]:
            self.play(GrowFromCenter(s), run_time=grow)
        self.play(*show(key), run_time=0.4)
        self.begin_ambient_camera_rotation(rate=0.25)
        peel = max(0.5, (total - self.renderer.time - 0.6) / max(1, n - 1))
        for k in range(n - 1, 0, -1):  # outermost first
            idx = n - 1 - k
            self.play(shells[k].animate.scale(1.25).set_opacity(0),
                      *[r.animate.set_opacity(1 if j == idx + 1 else 0.35) for j, r in enumerate(rows)],
                      run_time=peel * 0.6)
            self.remove(shells[k])
            self.move_camera(zoom=z0 * radii[-1] / radii[k - 1] * 0.75, run_time=peel * 0.4)
        self.wait(max(0.1, total - self.renderer.time))
