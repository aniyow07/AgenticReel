"""3D solids: named geometric solids spin in one after another, tumbling on two axes, each with its name and
its face/edge/vertex counts (built-in facts, not AI text) pinned below."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, OUT, RIGHT, Cone, Cube, Cylinder, Dodecahedron, GrowFromCenter, Icosahedron,  # noqa: E402
                   Octahedron, Sphere, Tetrahedron, ThreeDScene, Torus, VGroup)

from _common import DOWN, colors, fit_width, label, load_params, look_of, overlay, scene_seconds  # noqa: E402

FACTS = {
    "cube": ("Cube", "6 faces · 12 edges · 8 vertices"),
    "tetrahedron": ("Tetrahedron", "4 faces · 6 edges · 4 vertices"),
    "octahedron": ("Octahedron", "8 faces · 12 edges · 6 vertices"),
    "dodecahedron": ("Dodecahedron", "12 faces · 30 edges · 20 vertices"),
    "icosahedron": ("Icosahedron", "20 faces · 30 edges · 12 vertices"),
    "sphere": ("Sphere", "One curved surface, no edges"),
    "cylinder": ("Cylinder", "2 flat faces, 1 curved surface"),
    "cone": ("Cone", "1 flat face, 1 curved surface, 1 apex"),
    "torus": ("Torus", "A ring-shaped surface with a hole"),
}


def _make(name: str, C: dict):
    edge = {"stroke_color": C["accent"], "stroke_width": 3}
    poly = dict(faces_config={"fill_color": C["primary"], "fill_opacity": 0.7, "stroke_color": C["accent"],
                              "stroke_width": 2},
                graph_config={"vertex_config": {"radius": 0.05, "fill_color": C["accent"]}, "edge_config": edge})
    if name == "cube":
        return Cube(side_length=2.2, fill_color=C["primary"], fill_opacity=0.7, stroke_color=C["accent"],
                    stroke_width=2)
    if name in ("tetrahedron", "octahedron", "dodecahedron", "icosahedron"):
        cls = {"tetrahedron": Tetrahedron, "octahedron": Octahedron, "dodecahedron": Dodecahedron,
               "icosahedron": Icosahedron}[name]
        size = {"tetrahedron": 2.8, "octahedron": 2.4, "dodecahedron": 1.3, "icosahedron": 1.9}[name]
        return cls(edge_length=size, **poly)
    if name == "sphere":
        s = Sphere(radius=1.5, resolution=(14, 22))
    elif name == "cylinder":
        s = Cylinder(radius=1.1, height=2.4, resolution=(10, 24))
    elif name == "cone":
        s = Cone(base_radius=1.3, height=2.4, resolution=(10, 24)).shift(-OUT * 0.6)
    else:
        s = Torus(major_radius=1.4, minor_radius=0.5, resolution=(14, 24))
    s.set_fill_by_checkerboard(C["primary"], C["accent"], opacity=0.85)
    return s.set_stroke(C["background"], width=0.5)


class Solids3DScene(ThreeDScene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw = self.camera.frame_width
        shapes = [s for s in p.get("shapes", []) if s in FACTS][:4] or ["cube"]
        self.set_camera_orientation(phi=65 * DEGREES, theta=-40 * DEGREES, zoom=min(0.95, fw / 7.5))
        title, *_ = overlay(self, p, C, look)
        self.play(title.animate.set_opacity(1), run_time=0.4)
        slot = max(1.4, (total - 0.4) / len(shapes))
        for i, name in enumerate(shapes):
            solid = _make(name, C)
            spin = VGroup(solid)
            spin.add_updater(lambda m, dt: m.rotate(0.9 * dt, axis=OUT).rotate(0.35 * dt, axis=RIGHT))
            nm, fact = FACTS[name]
            tag = VGroup(label(nm, 30, C["accent"]), label(fact, 22, C["text"], weight="NORMAL"))
            fit_width(tag.arrange(DOWN, buff=0.1), fw * 0.84).to_edge(DOWN, buff=0.45)
            self.add_fixed_in_frame_mobjects(tag)
            tag.set_opacity(0)
            self.play(GrowFromCenter(spin), tag.animate.set_opacity(1), run_time=0.6)
            last = i == len(shapes) - 1
            self.wait(max(0.2, (total - self.renderer.time) if last else slot - 1.0))
            if not last:
                self.play(spin.animate.scale(0.01), tag.animate.set_opacity(0), run_time=0.4)
                spin.clear_updaters()
                self.remove(spin, tag)
