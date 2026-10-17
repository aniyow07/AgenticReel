"""Array algorithms run for real on the given numbers: bubble, selection and insertion sort swap bars,
linear and binary search narrow the range until the target is found. The template computes every step
itself, so the animation is always correct whatever the storyboard asked for."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (FadeIn, FadeOut, Flash, Indicate, Rectangle, Scene, SurroundingRectangle, Text,  # noqa: E402
                   VGroup, Write)

from _common import DOWN, UP, ambient, colors, fit_width, label, load_params, scene_seconds  # noqa: E402


def sort_steps(algo: str, a: list[int]) -> list[tuple]:
    """('cmp', i, j) and ('swap', i, j) events, plus ('done', k) when position k is final."""
    a = list(a)
    ev = []
    n = len(a)
    if algo == "bubble_sort":
        for end in range(n - 1, 0, -1):
            for i in range(end):
                ev.append(("cmp", i, i + 1))
                if a[i] > a[i + 1]:
                    a[i], a[i + 1] = a[i + 1], a[i]
                    ev.append(("swap", i, i + 1))
            ev.append(("done", end))
        ev.append(("done", 0))
    elif algo == "selection_sort":
        for i in range(n):
            m = i
            for j in range(i + 1, n):
                ev.append(("cmp", m, j))
                if a[j] < a[m]:
                    m = j
            if m != i:
                a[i], a[m] = a[m], a[i]
                ev.append(("swap", i, m))
            ev.append(("done", i))
    else:  # insertion_sort
        ev.append(("done", 0))
        for i in range(1, n):
            j = i
            while j > 0:
                ev.append(("cmp", j - 1, j))
                if a[j - 1] > a[j]:
                    a[j - 1], a[j] = a[j], a[j - 1]
                    ev.append(("swap", j - 1, j))
                    j -= 1
                else:
                    break
        ev += [("done", k) for k in range(n)]
    return ev


def search_steps(algo: str, a: list[int], target: int) -> list[tuple]:
    ev = []
    if algo == "binary_search":
        lo, hi = 0, len(a) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            ev.append(("range", lo, hi, mid))
            if a[mid] == target:
                ev.append(("found", mid))
                return ev
            lo, hi = (mid + 1, hi) if a[mid] < target else (lo, mid - 1)
    else:
        for i, v in enumerate(a):
            ev.append(("look", i))
            if v == target:
                ev.append(("found", i))
                return ev
    ev.append(("missing",))
    return ev


class ArrayAlgorithmScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        self.camera.background_color = C["background"]
        algo = p.get("algorithm", "bubble_sort")
        vals = [int(v) for v in p.get("values", [])][:10]
        if algo == "binary_search":
            vals = sorted(vals)
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        ambient(self, C, "array" + algo + "".join(map(str, vals)))

        title = fit_width(label(p.get("title", "") or algo.replace("_", " ").title(), 38, C["text"]), fw * 0.9)
        title.to_edge(UP, buff=0.4)
        n = len(vals)
        slot = min(0.9, fw * 0.86 / n)
        top = max(vals) or 1
        max_h = min(fh * 0.38, 4.2)
        bars = VGroup()
        for i, v in enumerate(vals):
            h = max(0.25, max_h * v / top)
            r = Rectangle(width=slot * 0.78, height=h, stroke_width=0, fill_color=C["primary"], fill_opacity=1)
            t = Text(str(v), font="Segoe UI", font_size=24, color=C["text"])
            bars.add(VGroup(r, t))
        base_y = -fh * 0.12
        for i, b in enumerate(bars):
            x = (i - (n - 1) / 2) * slot
            b[0].move_to([x, base_y + b[0].height / 2, 0])
            b[1].next_to(b[0], DOWN, buff=0.12)
        status_pos = [0, base_y - 1.1, 0]  # under the numbers
        status = VGroup()

        self.play(Write(title), FadeIn(bars, shift=UP * 0.2), run_time=1.0)
        searching = algo in ("binary_search", "linear_search")
        events = search_steps(algo, vals, int(p.get("target", vals[0]))) if searching else sort_steps(algo, vals)
        budget = max(1.0, total - 1.0 - 1.0)
        dt = max(0.12, min(0.7, budget / max(1, len(events))))

        def say(text):
            nonlocal status
            new = Text(text, font="Segoe UI", font_size=26, color=C["mutedText"]).move_to(status_pos)
            self.remove(status)
            self.add(new)
            status = new

        order = list(range(n))  # order[k] = index into bars of the bar at position k
        done_color = C["accent"]
        for ev in events:
            if ev[0] == "cmp":
                i, j = order[ev[1]], order[ev[2]]
                say(f"compare {vals_at(bars, i)} and {vals_at(bars, j)}")
                self.play(bars[i][0].animate.set_fill(C["mutedText"]), bars[j][0].animate.set_fill(C["mutedText"]),
                          run_time=dt * 0.5)
                self.play(bars[i][0].animate.set_fill(C["primary"]), bars[j][0].animate.set_fill(C["primary"]),
                          run_time=dt * 0.3)
            elif ev[0] == "swap":
                pi, pj = ev[1], ev[2]
                i, j = order[pi], order[pj]
                say("swap")
                xi, xj = bars[i][0].get_x(), bars[j][0].get_x()
                self.play(bars[i].animate.shift([xj - xi, 0, 0]), bars[j].animate.shift([xi - xj, 0, 0]),
                          run_time=dt)
                order[pi], order[pj] = j, i
            elif ev[0] == "done":
                b = bars[order[ev[1]]]
                b[0].set_fill(done_color)
            elif ev[0] == "range":
                lo, hi, mid = ev[1:]
                say(f"check middle: {vals[mid]}")
                for k, b in enumerate(bars):
                    b.set_opacity(1 if lo <= k <= hi else 0.25)
                self.play(Indicate(bars[mid], color=C["accent"], scale_factor=1.1), run_time=dt * 1.2)
            elif ev[0] == "look":
                say(f"is it {vals[ev[1]]}?")
                self.play(Indicate(bars[ev[1]], color=C["mutedText"], scale_factor=1.06), run_time=dt)
            elif ev[0] == "found":
                b = bars[ev[1]]
                b.set_opacity(1)
                say(f"found {vals[ev[1]]} at position {ev[1]}")
                box = SurroundingRectangle(b, color=C["accent"], buff=0.12, corner_radius=0.1)
                self.play(FadeIn(box), Flash(b[0].get_top(), color=C["accent"], num_lines=10), run_time=0.6)
            elif ev[0] == "missing":
                say("not in the list")
        if not searching:
            say("sorted")
            self.play(*[Indicate(b[0], color=done_color, scale_factor=1.04) for b in bars], run_time=0.7)
        self.wait(max(0.3, total - self.renderer.time))  # short searches hold the result for the rest of the scene


def vals_at(bars, i) -> str:
    return bars[i][1].text
