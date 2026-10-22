"""3D cube of facets: one idea with up to five sides, each written on a face of a cube. The cube turns to
show each side face in turn, lighting the face in front, then the camera rises to read the top face."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, RIGHT, FadeIn, ManimColor, Rotate, Square, ThreeDScene, VGroup,  # noqa: E402
                   interpolate_color, rate_functions)

from _common import clean, colors, label, load_params, look_of, overlay, scene_seconds, show, wrap  # noqa: E402


class CubeFaces3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        names = [clean(x)[:32] for x in p.get("faces", []) if str(x).strip()][:5]
        if len(names) < 2:
            raise ValueError("cube_faces_3d needs at least two faces")
        s = 2.8
        self.set_camera_orientation(phi=72 * DEGREES, theta=-90 * DEGREES, zoom=min(1.0, fw / 6.4),
                                    frame_center=[0, 0, s / 2])
        title, *notes = overlay(self, p, C, look, [p.get("caption", "")])
        lo, hi = ManimColor(C["primary"]), ManimColor(C["accent"])
        n = len(names)
        sides = min(n, 4)
        faces = []

        def face(text: str, col) -> VGroup:
            sq = Square(side_length=s, fill_color=col, fill_opacity=0.85, stroke_color=C["text"], stroke_width=2)
            t = label(wrap(text, 12, 3), 34, C["text"])
            if t.width > s * 0.82:
                t.scale_to_fit_width(s * 0.82)
            if t.height > s * 0.7:
                t.scale_to_fit_height(s * 0.7)
            # faces are depth-sorted so the nearest is drawn last; unsorted text always draws after every face,
            # which is why only the front face's text is ever visible
            sq.set_shade_in_3d(True)
            return VGroup(sq, t.shift(OUT * 0.01))

        for i in range(4):  # the four sides; unused sides stay blank
            col = interpolate_color(lo, hi, i / 4)
            f = face(names[i] if i < sides else "", col)
            f.rotate(90 * DEGREES, axis=RIGHT).shift([0, -s / 2, s / 2])  # readable from the camera's side
            f.rotate(i * 90 * DEGREES, axis=OUT, about_point=[0, 0, 0])  # i-th face is 90 degrees further round
            faces.append(f)
        top = face(names[4] if n == 5 else "", hi).shift([0, 0, s])
        top[1].rotate((sides - 1) * 90 * DEGREES, axis=OUT)  # upright again once the cube has turned
        base = Square(side_length=s, fill_color=C["surface"], fill_opacity=0.8, stroke_width=0)
        base.set_shade_in_3d(True)
        cube = VGroup(base, *faces, top)

        def shade(front: int):  # light the face in front, dim the rest
            anims = []
            for i, f in enumerate(faces):
                on = i == front
                anims.append(f[0].animate.set_fill(opacity=0.95 if on else 0.8))
                anims.append(f[1].animate.set_opacity(1 if on else 0))
            anims.append(top[1].animate.set_opacity(1 if front == -1 else 0))  # -1 = the top face
            return anims

        for i, f in enumerate(faces):
            if i:
                f[0].set_fill(opacity=0.8)
                f[1].set_opacity(0)
        top[1].set_opacity(0)
        self.play(*show(title), FadeIn(cube, shift=OUT * 1.2), run_time=0.7)
        self.play(*show(*notes), *shade(0), run_time=0.3)
        steps = sides - 1 + (1 if n == 5 else 0)
        step = max(0.5, (total - 1.4) / max(1, steps + 0.5))
        for k in range(1, sides):
            # turning the cube a quarter clockwise brings the next face round to the front
            self.play(Rotate(cube, -90 * DEGREES, axis=OUT, about_point=[0, 0, s / 2]),
                      run_time=step * 0.7, rate_func=rate_functions.ease_in_out_back)
            self.play(*shade(k), run_time=step * 0.3)
        if n == 5:
            self.move_camera(phi=18 * DEGREES, run_time=step * 0.8, added_anims=shade(-1))
        self.wait(max(0.1, total - self.renderer.time))
