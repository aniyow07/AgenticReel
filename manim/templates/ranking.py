"""A ranking that races into place. With values (from the sources) the bars grow at different paces and
overtake each other until they settle in order of value; without values the rows shuffle and swap into
the given order (first item is number one). The winner gets a crown flash."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (Circle, FadeIn, Flash, RoundedRectangle, Scene, Star, Text, ValueTracker, VGroup,  # noqa: E402
                   Write, rate_functions)

from _common import (FONT, LEFT, RIGHT, UP, ambient, clean, colors, fit_width, heading, label, load_params,  # noqa: E402
                     look_of, mix, num_text, scene_seconds)


class RankingScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 8.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        items = [clean(x)[:28] for x in p.get("items") or [] if str(x).strip()][:6]
        if len(items) < 2:
            raise ValueError("ranking needs at least two items")
        raw = p.get("values") or []
        values = [float(v) for v in raw][:len(items)] if len(raw) == len(items) else []
        unit = str(p.get("unit") or "")[:12]
        n = len(items)
        ambient(self, C, "ranking" + "".join(items))
        title = heading(p.get("title", ""), C, fw, look)
        order = sorted(range(n), key=lambda i: -values[i]) if values else list(range(n))
        rank = {i: r for r, i in enumerate(order)}  # final position of each item
        rng = random.Random("".join(items))
        start = list(range(n))
        while n > 1 and start == [rank[i] for i in range(n)]:
            rng.shuffle(start)

        top = title.get_bottom()[1] - 0.45
        row_h = min(1.0, (top - (-fh / 2 + 0.35)) / n)
        name_w, bar_x0 = fw * 0.3, -fw / 2 + 0.95 + fw * 0.3 + 0.15
        bar_max = fw / 2 - 0.35 - bar_x0 - (1.5 if values else 0)
        vmax = max(values) if values and max(values) > 0 else 1
        t = ValueTracker(0)
        speed = [rng.uniform(0.45, 2.2) for _ in range(n)]

        def frac(i):  # how far item i is through its race, with different paces so bars overtake
            x = t.get_value()
            return x ** speed[i] if values else x

        def slot_y(s):
            return top - row_h * (s + 0.5)

        def current_slot(i):
            if values:  # live order by current value, eased between slots
                cur = [values[j] * frac(j) for j in range(n)]
                return sum(1 for j in range(n) if cur[j] > cur[i] or (cur[j] == cur[i] and j < i))
            return start[i] + (rank[i] - start[i]) * rate_functions.smooth(t.get_value())

        rows = []
        for i, name in enumerate(items):
            col = mix(C["accent"], C["primary"], rank[i] / max(1, n - 1))
            badge = VGroup(Circle(radius=min(0.3, row_h * 0.36), fill_color=col, fill_opacity=1, stroke_width=0))
            tag = fit_width(label(name, 26, C["text"]), name_w)
            bar = RoundedRectangle(corner_radius=0.08, width=0.1, height=row_h * 0.56, stroke_width=0,
                                   fill_color=col, fill_opacity=0.9 if look != "glass" else 0.5)
            row = VGroup(badge, tag, bar, Text("0", font=FONT, font_size=22))
            row.i, row.y = i, slot_y(start[i])
            rows.append(row)

        def place(row):
            i = row.i
            target = slot_y(current_slot(i))
            row.y += (target - row.y) * 0.35  # glide toward the live slot instead of jumping
            badge, tag, bar = row[0], row[1], row[2]
            badge.move_to([-fw / 2 + 0.6, row.y, 0])
            tag.move_to([-fw / 2 + 0.95 + name_w / 2, row.y, 0]).align_to([-fw / 2 + 0.95, 0, 0], LEFT)
            w = max(0.1, bar_max * (values[i] * frac(i) / vmax if values else 0.35 + 0.65 * (1 - rank[i] / n)))
            bar.stretch_to_fit_width(w).move_to([bar_x0 + w / 2, row.y, 0])
            if values:
                row[3].become(Text(num_text(values[i] * frac(i), raw[i]) + unit, font=FONT, font_size=22,
                                   color=C["text"], weight="BOLD").next_to(bar, RIGHT, buff=0.12))
            else:
                row[3].set_opacity(0)

        for row in rows:
            row.y = slot_y(start[row.i])
            place(row)
            row.add_updater(place)
        nums = VGroup()
        self.play(Write(title), run_time=0.5)
        self.play(*[FadeIn(r, shift=RIGHT * 0.5) for r in rows], run_time=0.5)
        self.play(t.animate.set_value(1), run_time=max(1.2, total - 2.7), rate_func=rate_functions.ease_in_out_sine)
        self.wait(0.5)  # let the rows finish gliding into their final slots
        for r in rows:
            r.clear_updaters()
            r.y = slot_y(rank[r.i])
            place(r)
        for r in rows:  # rank numbers in the badges once the order is final
            nums.add(Text(str(rank[r.i] + 1), font=FONT, font_size=24, color=C["background"],
                          weight="BOLD").move_to(r[0]))
        winner = rows[order[0]]
        star = Star(n=5, outer_radius=0.22, fill_color=C["accent"], fill_opacity=1, stroke_width=0)
        star.move_to(winner[0].get_corner(UP + LEFT))
        self.play(FadeIn(nums, scale=1.6), FadeIn(star, scale=2), run_time=0.4)
        self.play(Flash(winner[2], color=C["accent"], flash_radius=0.5, num_lines=14),
                  winner.animate.scale(1.04), run_time=0.5)
        self.wait(max(0.1, total - self.renderer.time))
