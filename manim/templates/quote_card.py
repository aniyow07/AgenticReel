"""A quotation from the sources: an oversized quote mark swings in, the words appear one after another, the
highlighted phrase gets a marker swipe behind it, and the speaker's name slides in under a rule."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import (DEGREES, AnimationGroup, FadeIn, GrowFromEdge, Line, Rectangle, Scene, Text, VGroup, Write)  # noqa: E402

from _common import (DOWN, FONT, LEFT, RIGHT, UP, ambient, clean, colors, fit_width, heading, label,  # noqa: E402
                     load_params, look_of, scene_seconds)


class QuoteCardScene(Scene):
    def construct(self):
        p = load_params()
        C = colors(p)
        look = look_of(p)
        self.camera.background_color = C["background"]
        total = scene_seconds(p, 7.0)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        quote = " ".join(str(p.get("quote", "")).split())[:160]
        if not quote:
            raise ValueError("quote_card needs a quote")
        author = clean(p.get("author", ""))[:40]
        hl = [w.lower().strip(".,;:!?\"'") for w in str(p.get("highlight", "")).split()]
        ambient(self, C, "quote" + quote[:20])
        title = heading(p.get("title", ""), C, fw, look) if str(p.get("title", "")).strip() else VGroup()

        size = 40 if len(quote) < 60 else 34 if len(quote) < 110 else 28
        width = fw * 0.8
        tokens = quote.split()
        sizes = [Text(w, font=FONT, font_size=size, weight="BOLD").width for w in tokens]
        space = size / 100 * 0.32
        lines, row, x = [], [], 0.0
        for w, wd in zip(tokens, sizes):  # wrap the words into lines that fit the width
            if row and x + space + wd > width:
                lines.append(row)
                row, x = [], 0.0
            row.append(w)
            x += (space if len(row) > 1 else 0) + wd
        lines.append(row)
        # each line is one Text so the words share a baseline; its letters are then grouped back into words
        body, words = VGroup(), []
        for r in lines:
            line = Text(" ".join(r), font=FONT, font_size=size, color=C["text"], weight="BOLD")
            groups, k = VGroup(), 0
            if len(line.submobjects) != sum(len(w) for w in r):  # ligatures merged letters: keep the line whole
                line.word = " ".join(r)
                body.add(VGroup(line))
                words.append(line)
                continue
            for w in r:
                n = len(w.replace(" ", ""))
                g = VGroup(*line.submobjects[k:k + n])
                g.word = w
                groups.add(g)
                words.append(g)
                k += n
            body.add(groups)
        body.arrange(DOWN, buff=size / 100 * 0.35, aligned_edge=LEFT)
        top = (title.get_bottom()[1] if len(title) else fh / 2) - 1.3
        fit_width(body, width)
        if body.height > top + fh / 2 - 1.4:
            body.scale_to_fit_height(top + fh / 2 - 1.4)
        body.move_to([0, (top + (-fh / 2 + 1.3)) / 2 + 0.2, 0])
        mark = Text("“", font=FONT, font_size=220, color=C["accent"], weight="BOLD")
        mark.next_to(body, UP, buff=0.02).align_to(body, LEFT).shift(LEFT * 0.3)
        swipes = VGroup()
        targets = [w for w in words if hl and w.word.lower().strip(".,;:!?\"'“”") in hl]
        for w in targets:
            r = Rectangle(width=w.width + 0.14, height=w.height * 0.55, stroke_width=0, fill_color=C["accent"],
                          fill_opacity=0.45).move_to(w.get_bottom() + UP * w.height * 0.3)
            swipes.add(r)
        rule = Line(LEFT * 0.5, RIGHT * 0.5, color=C["accent"], stroke_width=5)
        who = VGroup()
        if author:
            who = VGroup(rule, fit_width(label(author, 26, C["mutedText"]), fw * 0.6)).arrange(RIGHT, buff=0.25)
            who.next_to(body, DOWN, buff=0.55).align_to(body, LEFT)

        self.play(*([Write(title)] if len(title) else []),
                  FadeIn(mark.rotate(-25 * DEGREES), scale=2.2, shift=DOWN * 0.4), run_time=0.6)
        self.play(mark.animate.rotate(25 * DEGREES), run_time=0.3)
        flat = words
        reveal = max(1.0, (total - 2.4) * 0.75)
        self.play(AnimationGroup(*[FadeIn(w, shift=UP * 0.15) for w in flat], lag_ratio=0.35), run_time=reveal)
        if len(swipes):
            self.add_foreground_mobjects(*flat)
            self.play(*[GrowFromEdge(s, LEFT) for s in swipes], *[w.animate.set_color(C["text"]) for w in targets],
                      run_time=0.5)
        if author:
            self.play(GrowFromEdge(rule, LEFT), FadeIn(who[1], shift=RIGHT * 0.4), run_time=0.5)
        self.play(mark.animate.scale(1.08).set_opacity(0.8), run_time=max(0.1, total - self.renderer.time - 0.05))
