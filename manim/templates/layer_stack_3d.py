"""3D layer stack: seen from straight above, named slabs drop into a stack one by one (bottom layer first),
then the camera tips down to the side while the stack pulls apart into an exploded view."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import DEGREES, OUT, FadeIn, ManimColor, Prism, Text, ThreeDScene, VGroup, interpolate_color  # noqa: E402

from _common import FONT, clean, colors, load_params, look_of, overlay, scene_seconds, show  # noqa: E402


class LayerStack3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:24] for x in p.get("layers", []) if str(x).strip()][:6]
        if len(names) < 2:
            raise ValueError("layer_stack_3d needs at least two layers")
        n = len(names)
        W, D, T = 3.6, 2.4, 0.3
        self.set_camera_orientation(phi=0, theta=-90 * DEGREES, zoom=min(0.95, fw / 6.5))
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        lo, hi = ManimColor(C["primary"]), ManimColor(C["accent"])

        slabs = []
        for i, name in enumerate(names):  # i = 0 is the top layer
            k = n - 1 - i  # height index from the bottom
            col = interpolate_color(hi, lo, i / max(1, n - 1))
            box = Prism(dimensions=[W, D, T], fill_opacity=0.92, stroke_width=1.2, stroke_color=C["background"])
            box.set_fill(col)
            t = Text(name, font=FONT, font_size=34, color=C["text"], weight="BOLD")
            if t.width > W * 0.85:
                t.scale_to_fit_width(W * 0.85)
            t.move_to([0, -D / 2 + 0.42, T / 2 + 0.01])  # near the front edge, so the layer above never covers it
            slab = VGroup(box, t).move_to([0, 0, k * T])
            slab.k = k
            slabs.append(slab)

        drop = min(0.55, max(0.3, (total - 4) / n))
        self.play(*show(title), run_time=0.4)
        below = None
        for slab in reversed(slabs):  # bottom first, so each new layer lands on top
            # seen from above, names on the layers underneath would show through: hide them until the split
            self.play(FadeIn(slab, shift=-OUT * 2.5), *([below[1].animate.set_opacity(0)] if below else []),
                      run_time=drop)
            below = slab
        spread = 0.95 if n <= 4 else 0.7
        mid = (n - 1) * (T + spread) / 2
        rest = max(1.2, total - self.renderer.time - 0.2)
        self.move_camera(phi=52 * DEGREES, theta=-60 * DEGREES, zoom=min(0.85, fw / (5 + 0.9 * n)),
                         added_anims=[*[m.animate.shift(OUT * (s.k * (T + spread) - mid - s[0].get_z()))
                                        .set_opacity(1 if m is s[1] else 0.92) for s in slabs for m in s],
                                      *show(*notes)], run_time=rest * 0.7)
        self.begin_ambient_camera_rotation(rate=0.12)
        self.wait(max(0.1, total - self.renderer.time))
