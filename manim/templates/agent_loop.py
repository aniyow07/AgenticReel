"""An AI agent at work: the goal comes in, the agent cycles through its loop (plan, act, observe ...),
calls its tools along the way (a signal travels out to the tool and back), and finishes with the result."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Arc, Circle, Create, FadeIn, Flash, GrowFromCenter, Indicate, Line, MoveAlongPath,  # noqa: E402
                   RoundedRectangle, Scene, VGroup, Write, Dot, DashedLine)

from _common import DOWN, UP, ambient, colors, fit_width, label, load_params, scene_seconds, stream  # noqa: E402


def node(text, C, w, h, stroke, size=26):
    r = RoundedRectangle(corner_radius=0.18, width=w, height=h, stroke_color=stroke, stroke_width=4,
                         fill_color=C["surface"], fill_opacity=1)
    t = fit_width(label(text, size, C["text"]), w - 0.25).move_to(r)
    return VGroup(r, t)


class AgentLoopScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        steps = [s for s in p.get("steps", []) if str(s).strip()][:6] or ["Plan", "Act", "Observe"]
        tools = [s for s in p.get("tools", []) if str(s).strip()][:4]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "agent" + "".join(steps + tools))

        title = fit_width(label(p.get("title", ""), 38, C["text"]), fw * 0.9).to_edge(UP, buff=0.4)
        goal_txt = p.get("goal", "")
        goal = node("Goal: " + goal_txt if goal_txt else "Goal", C, fw * 0.82, 0.75, C["accent"], 24)
        goal.next_to(title, DOWN, buff=0.35)

        # the loop: steps on a circle around the agent
        R = min(fw * 0.32, fh * 0.17)
        cy = goal.get_bottom()[1] - 0.6 - R - 0.4
        center = [0, cy, 0]
        agent = VGroup(Circle(radius=0.62, stroke_color=C["accent"], stroke_width=5, fill_color=C["surface"],
                              fill_opacity=1), label(p.get("agent", "Agent") or "Agent", 26, C["text"]))
        agent.move_to(center)
        ring = Circle(radius=R, stroke_color=C["primary"], stroke_width=3, stroke_opacity=0.5).move_to(center)
        nodes = VGroup()
        for k, s in enumerate(steps):
            ang = math.pi / 2 - 2 * math.pi * k / len(steps)
            nd = node(s, C, min(2.3, fw * 0.36), 0.62, C["primary"], 22)
            nd.move_to([R * math.cos(ang), cy + R * math.sin(ang), 0])
            nodes.add(nd)

        tool_nodes = VGroup(*[node(t, C, min(2.0, fw * 0.8 / max(1, len(tools)) - 0.15), 0.6, C["mutedText"], 20)
                              for t in tools])
        if tools:
            tool_nodes.arrange(UP * 0 + [1, 0, 0], buff=0.2)
            tool_nodes.move_to([0, cy - R - 1.05, 0])
            if tool_nodes.width > fw * 0.92:
                tool_nodes.scale_to_fit_width(fw * 0.92)
        result = node(p.get("result", "") or "Done", C, fw * 0.7, 0.7, C["accent"], 24)
        result.move_to([0, (tool_nodes.get_bottom()[1] if tools else cy - R - 0.4) - 0.75, 0])
        if result.get_bottom()[1] < -fh / 2 + 0.2:
            result.shift(UP * (-fh / 2 + 0.2 - result.get_bottom()[1]))

        self.play(Write(title), FadeIn(goal, shift=DOWN * 0.2), run_time=0.8)
        self.play(GrowFromCenter(agent), Create(ring), run_time=0.6)
        self.play(*[FadeIn(nd, scale=0.8) for nd in nodes], run_time=0.6)
        if tools:
            links = VGroup(*[DashedLine(agent.get_bottom(), t.get_top(), color=C["mutedText"], stroke_width=2)
                             for t in tool_nodes])
            self.play(FadeIn(tool_nodes, shift=UP * 0.2), Create(links), run_time=0.6)
        self.add(stream(ring, C["accent"], count=3, speed=0.35, radius=0.07))

        loops = 2 if len(steps) <= 4 else 1
        visits = loops * len(steps)
        budget = max(1.5, total - 0.8 - 0.6 - 0.6 - (0.6 if tools else 0) - 1.0)
        each = budget / visits
        act_idx = next((k for k, s in enumerate(steps) if any(w in s.lower() for w in ("act", "tool", "call", "run",
                                                                                         "execute", "search"))), 1 % len(steps))
        for v in range(visits):
            k = v % len(steps)
            nd = nodes[k]
            # light the box and keep its label readable on top of it
            anims = [Indicate(nd[0], color=C["accent"], scale_factor=1.12),
                     Indicate(nd[1], color=C["background"], scale_factor=1.12)]
            self.play(*anims, run_time=each * (0.5 if tools and k == act_idx else 1))
            if tools and k == act_idx:
                t = tool_nodes[(v // len(steps)) % len(tool_nodes)]
                ping = Dot(radius=0.08, color=C["accent"]).move_to(agent.get_bottom())
                go = Line(agent.get_bottom(), t.get_top())
                self.add(ping)
                self.play(MoveAlongPath(ping, go), Indicate(t[0], color=C["accent"]),
                          Indicate(t[1], color=C["background"]), run_time=each * 0.3)
                self.play(MoveAlongPath(ping, Line(t.get_top(), agent.get_bottom())), run_time=each * 0.2)
                self.remove(ping)
        self.play(FadeIn(result, shift=UP * 0.2), Flash(result, color=C["accent"], num_lines=12,
                                                        flash_radius=result.width / 2 + 0.2), run_time=0.8)
        self.wait(0.2)
