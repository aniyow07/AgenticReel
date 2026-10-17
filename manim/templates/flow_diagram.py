"""Flow diagram: inputs stream into a spinning hub that streams out to the outputs."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arrow, Circle, Create, DashedVMobject, FadeIn, GrowArrow, Indicate, LaggedStart,  # noqa: E402
                   Line, RoundedRectangle, Scene, VGroup, Write)

from _common import (DOWN, LEFT, RIGHT, UP, ambient, colors, fit_width, label, load_params,  # noqa: E402
                     scene_seconds, stream)


def _node(text: str, width: float, color: str, C: dict) -> VGroup:
    t = fit_width(label(text, 26, C["text"]), width * 0.88)
    r = RoundedRectangle(corner_radius=0.15, width=width, height=max(0.8, t.height + 0.4),
                         stroke_color=color, stroke_width=4, fill_color=C["surface"], fill_opacity=1)
    t.move_to(r)
    return VGroup(r, t)


class FlowDiagramScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        inputs = [s for s in p.get("inputs", []) if str(s).strip()][:4]
        outputs = [s for s in p.get("outputs", []) if str(s).strip()][:4]
        center = str(p.get("center", "")).strip()
        if not inputs or not outputs or not center:
            raise ValueError("flow_diagram needs inputs, a center and outputs")
        total = scene_seconds(p, 6.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "flow" + center)
        col_w = fw * 0.28

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        ins = VGroup(*[_node(s, col_w, C["primary"], C) for s in inputs]).arrange(DOWN, buff=0.35)
        outs = VGroup(*[_node(s, col_w, C["accent"], C) for s in outputs]).arrange(DOWN, buff=0.35)
        hub_r = min(col_w * 0.5, 1.3)
        hub_label = fit_width(label(center, 26, C["text"]), hub_r * 1.7)
        core = Circle(radius=hub_r, color=C["accent"], stroke_width=6, fill_color=C["surface"], fill_opacity=1)
        hub = VGroup(core, hub_label)
        body = VGroup(ins, hub, outs).arrange(RIGHT, buff=fw * 0.06)
        fit_width(body, fw * 0.94)
        if body.height > fh - 1.6:
            body.scale_to_fit_height(fh - 1.6)
        body.move_to([0, (title.get_bottom()[1] - fh / 2) / 2, 0])

        ring = DashedVMobject(Circle(radius=core.width / 2 * 1.18, color=C["primary"], stroke_width=4),
                              num_dashes=24).move_to(core)
        ring.add_updater(lambda m, dt: m.rotate(0.9 * dt))
        a_in = [Arrow(n.get_right(), core.get_left(), buff=0.08, color=C["primary"], stroke_width=5) for n in ins]
        a_out = [Arrow(core.get_right(), n.get_left(), buff=0.08, color=C["accent"], stroke_width=5) for n in outs]
        p_in = [Line(n.get_right(), core.get_left()) for n in ins]
        p_out = [Line(core.get_right(), n.get_left()) for n in outs]

        seg = (total - 0.6) / 5
        self.play(Write(title), run_time=0.6)
        self.play(LaggedStart(*[FadeIn(n, shift=RIGHT * 0.3) for n in ins], lag_ratio=0.3), run_time=seg)
        self.play(*[GrowArrow(a) for a in a_in], Create(core), FadeIn(hub_label), run_time=seg)
        self.add(ring, *[stream(pth, C["primary"], count=3, speed=0.8) for pth in p_in])
        self.play(Indicate(hub, color=C["accent"], scale_factor=1.08), run_time=seg * 0.6)
        self.play(*[GrowArrow(a) for a in a_out], run_time=seg * 0.6)
        self.add(*[stream(pth, C["accent"], count=3, speed=0.8) for pth in p_out])
        self.play(LaggedStart(*[FadeIn(n, shift=LEFT * 0.3) for n in outs], lag_ratio=0.3), run_time=seg)
        self.play(LaggedStart(*[Indicate(n[0], color=C["accent"], scale_factor=1.06) for n in outs], lag_ratio=0.4),
                  run_time=seg * 0.8)
        self.wait(max(0.1, seg * 1.0))
