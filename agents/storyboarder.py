"""Agent 4: Storyboarder -> storyboard.json

The storyboard only *describes* scenes with parameters for trusted renderers.
It never contains code. Planned times are estimates from the word count; the
Editor later replaces them with measured narration timings.
"""
from __future__ import annotations

import re

import random

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agents import template_catalog
from agents.base import AgentContext, ask_llm
from core.mathtext import clean_tree, latex_to_unicode
from retrieval.index import tokenize
from rendering import manim_runner
from schemas.artifacts import Facts, Plan, Script, Storyboard, StoryboardScene
from schemas.render_props import BACKDROP_STYLES, PARAM_MODELS, VISUAL_TYPES_OG

PROMPT_VERSION = "storyboarder/v9"

SYSTEM = """You are the Storyboarder agent for an OG motion-graphics video. Group consecutive narration segments
into scenes and choose a trusted visual for each. Allowed visual_type values and their visual_parameters:
- title: {"title": str, "subtitle": str}
- text_reveal: {"text": str}
- key_points: {"heading": str, "points": [2-5 short strings]}
- stat: {"value": number, "prefix": str, "suffix": str, "label": str, "sourceNote": str}  (ONLY numbers from supported facts)
- timeline: {"heading": str, "events": [{"label": str, "detail": str}] (2-6)}
- process: {"heading": str, "steps": [2-6 short strings]}
- comparison: {"heading": str, "leftTitle": str, "rightTitle": str, "leftPoints": [..], "rightPoints": [..]}
- chart: {"heading": str, "labels": [..], "values": [numbers], "unit": str, "sourceNote": str} (ONLY supplied numbers)
- manim: a Manim animation. manim_template is a whole OBJECT holding "template" AND every field the catalog
  lists for it, never just a name. Example scene:
  {"segment_ids": ["N03"], "visual_type": "manim", "visual_parameters": {"heading": ""},
   "manim_template": {"template": "array_algorithm", "title": "Example: quick sort", "algorithm": "quick_sort",
   "values": [6, 3, 8, 2, 9, 4, 7]}, "template_reason": "shows the partition steps"}
  Catalog (name: use when. {the object to write}):
{catalog}
  Picking templates: read the whole catalog before choosing; it is not ranked. Most middle scenes should be
  Manim (all but one when there are three or more). When the video explains how something works, use the
  animation made for it (array_algorithm for sorting and searching, equation_steps for worked math,
  function_plot for graphs of functions, node_graph for networks and graph algorithms, chemical_reaction,
  agent_loop, security_flow, the 3D science scenes) before any general template. Never use the same
  template twice in one video. process_diagram and flow_diagram are last resorts for when nothing else fits.
  Mix groups across the video (for example a topic animation, a comparison and a 3D scene rather than three
  step diagrams). Use at most two 3D templates per video, never two in a row. Every number and year on
  screen must come from the supported facts or be said in that scene's narration; the only exception is the
  small example list an array_algorithm sorts or searches (title it "Example: ..."). Captions are short
  (under 40 characters) and only say what the narration says. Only show equations, formulas and names the
  narration states.
- end_card: {"text": str, "cta": str}
Give each scene a "backdrop" (animated background). Match the mood: grid (technical, data), waves (calm,
flowing), rays (big reveal), shapes (playful), orbs (neutral), aurora (dreamy, nature, space),
constellation (networks, AI, connections), hexgrid (science, chemistry, structure), circuit (computing,
electronics, software), contours (geography, physics, maps), stripes (energetic, fast facts), matrix (code,
hacking, cybersecurity). Use a variety across the video and avoid
using the same backdrop twice in a row.
Use the first scene as a title and the last as an end_card. Every segment id must be used exactly once, in order.
Keep on-screen text short (under 8 words per item). Return ONLY JSON:
{"scenes": [{"segment_ids": [...], "visual_type": "...", "visual_parameters": {...}, "on_screen_text": "",
 "transition": "fade|slide|zoom", "backdrop": "grid", "manim_template": null, "template_reason": ""}]}"""


# where models put a template's fields when they do not write them inside manim_template itself
_FIELD_HOMES = ("params", "parameters", "fields", "data", "template_params", "template_parameters",
                "manim_params", "manim_parameters", "manim_data", "template_data")
_SCENE_KEYS = {"segment_ids", "visual_type", "visual_parameters", "on_screen_text", "transition", "backdrop",
               "manim_template", "template_reason"}


class SceneLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    segment_ids: list[str] = Field(default_factory=list)  # empty scenes are dropped by fix_coverage
    visual_type: str
    visual_parameters: dict = Field(default_factory=dict)
    on_screen_text: str = ""
    transition: str = "fade"
    backdrop: str = ""
    manim_template: dict | None = None
    template_reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _template_name(cls, d):
        """Models often write "manim_template": "mind_map" (a bare name, its fields in visual_parameters) or
        use the template name as the visual_type. Both mean the same scene, so accept them instead of
        rejecting the whole storyboard and paying for a second AI call."""
        if not isinstance(d, dict):
            return d
        vt, mt, vp = d.get("visual_type"), d.get("manim_template"), d.get("visual_parameters")
        vp = vp if isinstance(vp, dict) else {}
        if isinstance(vt, str) and vt in manim_runner.TEMPLATES and vt != "timeline":
            d = {**d, "visual_type": "manim", "manim_template": mt if isinstance(mt, dict) else vt}
            mt = d["manim_template"]
        if isinstance(mt, str) and mt in manim_runner.TEMPLATES:
            mt = {"template": mt}
        elif isinstance(mt, str):
            return {**d, "manim_template": None}
        if isinstance(mt, dict) and mt.get("template") in manim_runner.TEMPLATES:
            # the template's fields may sit in visual_parameters, at the scene's top level, or one level down in
            # a "params"-like object: gather them all; what the template object itself says wins
            fields = {k: v for k, v in vp.items() if k != "heading"}
            fields.update({k: v for k, v in d.items() if k not in _SCENE_KEYS and k not in _FIELD_HOMES})
            for src in (d, vp, mt):
                for k in _FIELD_HOMES:
                    if isinstance(src.get(k), dict):
                        fields.update(src[k])
            fields.update({k: v for k, v in mt.items() if k not in _FIELD_HOMES})
            if "heading" in vp and not fields.get("title"):
                fields["title"] = vp["heading"]
            d = {**{k: v for k, v in d.items() if k in _SCENE_KEYS}, "manim_template": fields}
        return d


class StoryboardLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    scenes: list[SceneLLM] = Field(min_length=1, max_length=14)


def shorten(text: str, n: int = 8) -> str:
    words = re.sub(r"[.!?]+$", "", text.strip()).split()
    s = " ".join(words[:n])
    return s + ("…" if len(words) > n else "")


def _same(a: str, b: str) -> bool:
    n = lambda s: re.sub(r"\W+", " ", s.lower()).strip(" .")  # noqa: E731
    return n(a).startswith(n(b)[:30]) or n(b).startswith(n(a).rstrip("…")[:30])


def _groups(ids: list[str], count: int) -> list[list[str]]:
    count = max(1, min(count, len(ids)))
    size, rem = divmod(len(ids), count)
    out, i = [], 0
    for k in range(count):
        n = size + (1 if k < rem else 0)
        out.append(ids[i:i + n])
        i += n
    return [g for g in out if g]


def _numbers_in_facts(facts: Facts) -> str:
    return " ".join(f.evidence + " " + f.claim for f in facts.supported()).replace(",", "")


# templates the local fallback can fill from narration lines alone, and the list field each one takes
LOCAL_TEMPLATES = {"roadmap": "stops", "domino_chain": "links", "cycle_diagram": "stages", "carousel_3d": "items",
                   "process_diagram": "steps"}


def local_template(fits: list[str], job_id: str, title: str, items: list[str]) -> dict:
    """A Manim template built from narration lines only: the best topic fit the fallback can fill, otherwise a
    per-video rotation, so a run without the AI does not always get the same process diagram."""
    usable = [t for t, f in LOCAL_TEMPLATES.items() if t != "carousel_3d" or len(items) >= 3]
    usable = [t for t in usable if t != "cycle_diagram" or len(items) >= 3]
    pick = next((t for t in fits if t in usable), None)
    if not pick:
        # a cause chain or a loop says something about the content, so it is never just a rotation pick
        rot = [t for t in usable if t not in ("process_diagram", "domino_chain", "cycle_diagram")] or ["process_diagram"]
        pick = rot[sum(map(ord, job_id)) % len(rot)]
    return {"template": pick, "title": title, LOCAL_TEMPLATES[pick]: items}


def local_storyboard(ctx: AgentContext, plan: Plan, script: Script, facts: Facts,
                     fits: list[str] | None = None) -> StoryboardLLM:
    segs = script.segments
    ids = [s.segment_id for s in segs]
    text = {s.segment_id: s.text for s in segs}
    if ctx.brief.mode != "og":
        return StoryboardLLM(scenes=[SceneLLM(segment_ids=g, visual_type="gameplay", transition="none")
                                     for g in _groups(ids, max(2, len(ids) // 2))])
    if len(ids) < 3:
        return StoryboardLLM(scenes=[SceneLLM(segment_ids=ids, visual_type="title", visual_parameters={
            "title": script.title, "subtitle": ctx.brief.audience})])
    middle = _groups(ids[1:-1], max(1, plan.scene_count - 2))
    scenes = [SceneLLM(segment_ids=[ids[0]], visual_type="title",
                       visual_parameters={"title": script.title, "subtitle": f"For {ctx.brief.audience}"})]
    numbers = _numbers_in_facts(facts)
    manim_used = False
    # a cause chain or a loop only when the topic clearly is one; the variety pass adds the rest
    strong = [t for t in fits or [] if t in template_catalog.fits(topic_text(ctx, script), min_hits=2)]
    for gi, g in enumerate(middle):
        points = [shorten(text[i]) for i in g]
        fact = next((f for i in g for s in segs if s.segment_id == i for fid in s.fact_ids
                     for f in facts.supported() if f.fact_id == fid and f.status == "supported"), None)
        num = re.search(r"(\d+(?:\.\d+)?)\s*(%|percent)?", fact.claim) if fact else None
        if num and num.group(1) in numbers:
            scenes.append(SceneLLM(segment_ids=g, visual_type="stat", visual_parameters={
                "value": float(num.group(1)), "suffix": "%" if num.group(2) else "", "label": shorten(fact.claim, 9),
                "sourceNote": f"{fact.source}{', p. ' + str(fact.page) if fact.page else ''}"}))
        elif plan.manim_scenes and not manim_used and len(g) >= 2 and gi == len(middle) // 2:
            manim_used = True
            steps = [shorten(text[i], 5) for i in g][:5]
            scenes.append(SceneLLM(segment_ids=g, visual_type="manim", visual_parameters={"heading": ""},
                                   manim_template=local_template(strong, ctx.job.id, shorten(
                                       plan.manim_scenes[0].capitalize(), 6), steps)))
        elif gi % 2 == 0 and len(points) >= 2:
            scenes.append(SceneLLM(segment_ids=g, visual_type="key_points",
                                   visual_parameters={"heading": "", "points": points[:5]}, transition="slide"))
        else:
            scenes.append(SceneLLM(segment_ids=g, visual_type="text_reveal", visual_parameters={"text": text[g[0]]},
                                   transition="zoom"))
    closing = shorten(text[ids[-1]], 9)
    if script.cta and _same(closing, script.cta):
        closing = script.title
    scenes.append(SceneLLM(segment_ids=[ids[-1]], visual_type="end_card",
                           visual_parameters={"text": closing, "cta": script.cta[:60]}))
    return StoryboardLLM(scenes=scenes)


def sanitize(ctx: AgentContext, sb: StoryboardLLM, script: Script, facts: Facts) -> tuple[StoryboardLLM, list[str]]:
    """Replace invalid or unsupported visuals with safe ones instead of failing the job."""
    notes = []
    text = {s.segment_id: s.text for s in script.segments}
    numbers = _numbers_in_facts(facts)
    grounding = None if ctx.brief.content_type == "fictional_story" else grounding_corpus(ctx, script, facts)
    n_3d, used, prev_3d = 0, set(), False
    topic = topic_text(ctx, script)
    for sc in sb.scenes:
        was_3d, prev_3d = prev_3d, False
        # models write equations in LaTeX; there is no LaTeX on screen, so turn it into Unicode math first
        sc.on_screen_text = latex_to_unicode(sc.on_screen_text)
        sc.visual_parameters = clean_tree(sc.visual_parameters)
        sc.manim_template = clean_tree(sc.manim_template)
        if ctx.brief.mode != "og":
            sc.visual_type, sc.visual_parameters, sc.manim_template = "gameplay", {}, None
            continue
        if sc.transition not in ("fade", "slide", "zoom", "none"):
            sc.transition = "fade"
        fallback = {"text": text.get(sc.segment_ids[0], "")}
        if sc.visual_type not in VISUAL_TYPES_OG or sc.visual_type == "image":
            notes.append(f"unsupported visual {sc.visual_type!r} replaced with text_reveal")
            sc.visual_type, sc.visual_parameters = "text_reveal", fallback
            continue
        if sc.visual_type in ("stat", "chart"):
            vals = [sc.visual_parameters.get("value")] if sc.visual_type == "stat" else \
                sc.visual_parameters.get("values", [])
            said = numbers + " " + " ".join(text.get(i, "") for i in sc.segment_ids).replace(",", "")
            if not vals or any(v is None or f"{float(v):g}" not in said for v in vals if v is not None):
                notes.append(f"{sc.visual_type} scene used numbers not found in supported facts; replaced")
                sc.visual_type, sc.visual_parameters = "text_reveal", fallback
                continue
        if sc.visual_type == "manim":
            scene_lines = [text.get(i, "") for i in sc.segment_ids]
            scene_text = " ".join(scene_lines)
            mt, rebuilt = sc.manim_template, None
            try:
                try:
                    mt = check_manim(mt, numbers, grounding, scene_text)
                except (ValueError, ValidationError, TypeError) as e:
                    # the AI chose a template but its data is missing or broken: fill the same template from
                    # the scene's own narration (or a labelled example for a topic animation) before giving up
                    name = (mt or {}).get("template") if isinstance(mt, dict) else None
                    rebuilt = template_catalog.build(name, (mt or {}).get("title") or sc.on_screen_text,
                                                     template_catalog.phrases(scene_lines), topic, scene_lines) \
                        if name else None
                    if not rebuilt:
                        raise
                    mt = check_manim(rebuilt, numbers, grounding, scene_text)
                    notes.append(f"{name} data rebuilt from the scene's narration ({str(e).splitlines()[0][:80]})")
                sc.manim_template = mt
                tpl = mt["template"]
                if tpl in used:
                    raise _Repeat(f"{tpl} was already used in this video")
                if tpl in manim_runner.THREE_D:
                    # 3D clips are the slowest to render and lose impact when repeated
                    if n_3d >= MAX_3D_SCENES:
                        raise _Repeat(f"more than {MAX_3D_SCENES} 3D scenes")
                    if was_3d:
                        raise _Repeat("two 3D scenes in a row")
                    n_3d += 1
                    prev_3d = True
                used.add(tpl)
            except _Repeat as e:
                # the data is valid, only the variety rule failed: show the same data as a Remotion visual
                notes.append(f"Manim template replaced with a Remotion scene for variety: {e}")
                alt = manim_runner.remotion_fallback(sc.manim_template)
                try:
                    if not alt:
                        raise ValueError("no Remotion equivalent")
                    sc.visual_type = alt[0]
                    sc.visual_parameters = PARAM_MODELS[alt[0]].model_validate(alt[1]).model_dump()
                except (ValueError, ValidationError):
                    sc.visual_type, sc.visual_parameters = "text_reveal", fallback
                sc.manim_template = None
            except (ValueError, ValidationError, TypeError) as e:
                notes.append(f"invalid Manim template replaced with a Remotion process/text scene: {e}")
                steps = (sc.manim_template or {}).get("steps") or []
                if 2 <= len(steps) <= 6 and all(isinstance(x, str) for x in steps):
                    sc.visual_type, sc.visual_parameters = "process", {"heading": "", "steps": steps}
                else:
                    sc.visual_type, sc.visual_parameters = "text_reveal", fallback
                sc.manim_template = None
            continue
        try:
            PARAM_MODELS[sc.visual_type].model_validate(sc.visual_parameters)
        except ValidationError as e:
            notes.append(f"{sc.visual_type} params invalid ({e.error_count()} errors); replaced with text_reveal")
            sc.visual_type, sc.visual_parameters = "text_reveal", fallback
            continue
        if grounding is not None:
            scene_text = " ".join(text.get(i, "") for i in sc.segment_ids)
            params, gnotes = ground_params(sc.visual_type, sc.visual_parameters, grounding, scene_text,
                                           ctx.brief.cta)
            notes.extend(f"{sc.visual_type}: {n}" for n in gnotes)
            try:
                sc.visual_parameters = PARAM_MODELS[sc.visual_type].model_validate(params).model_dump()
            except ValidationError:
                notes.append(f"{sc.visual_type} had too little grounded text left; replaced with text_reveal")
                sc.visual_type, sc.visual_parameters = "text_reveal", fallback
    return sb, notes


def topic_text(ctx: AgentContext, script: Script) -> str:
    return " ".join([ctx.brief.topic, script.title, *(s.text for s in script.segments)]).lower()


def check_manim(mt: dict | None, numbers: str, grounding: dict | None, scene_text: str) -> dict:
    """A Manim pick, repaired and checked: valid fields, numbers from the supported facts or the scene's own
    narration (an array_algorithm's example list is exempt: it is titled as an example), and the general
    templates' text grounded in the sources. Returns the repaired template or raises ValueError."""
    if not mt:
        raise ValueError("missing manim_template")
    mt = template_catalog.repair(mt)
    tpl = mt.get("template")
    if tpl == "array_algorithm" and "example" not in str(mt.get("title", "")).lower():
        mt = {**mt, "title": ("Example: " + str(mt.get("title") or "")).strip(" :")[:80]}
    if tpl in manim_runner.NUMBER_FIELDS or tpl == "line_chart":
        said = numbers + " " + scene_text.replace(",", "")
        vals = [v for s in mt.get("series", []) for v in (s.get("values") or [])] if tpl == "line_chart" \
            else [v for k in manim_runner.NUMBER_FIELDS[tpl]
                  for v in (mt.get(k) if isinstance(mt.get(k), list) else [mt.get(k)]) if v is not None]
        if any(f"{float(v):g}" not in said for v in vals):
            raise ValueError("chart values are not in supported facts")
    manim_runner.validate(mt)
    if tpl in manim_runner.GENERAL and grounding is not None:
        check_general_text(mt, grounding, scene_text)
    return mt


# ---------------- variety pass (code, after the AI and the validator) ----------------
REMOTION_SOURCES = ("chart", "stat", "comparison", "timeline", "process", "key_points")  # best data first


def manim_target(middle: int) -> int:
    """How many middle scenes should be Manim: all of up to three, all but one of four or more."""
    return middle if middle <= 3 else middle - 1


def diversify(ctx: AgentContext, sb: StoryboardLLM, script: Script, facts: Facts,
              weights: dict[str, float]) -> list[str]:
    """Make each video use more, more fitting and less repetitive Manim templates, with no AI call:
    1. a video about something a topic animation explains (sorting, graph search, a molecule) gets that
       animation when the AI left it out, on a text or Remotion scene, else on a general Manim scene;
    2. a template the user's recent videos used a lot (or a generic process/flow diagram) is swapped for an
       unused template that shows the very same data (template_catalog.alternatives), if that one was used less;
       a generic or very overused one may also become another layout of its narration's phrases; topic
       animations (sorting, equations, graphs, 3D science) are never swapped away;
    3. while fewer middle scenes than manim_target() are Manim, a Remotion or text scene becomes the best
       template that can show its data or its narration: a topic animation that fits first, then the least
       recently used general template;
    4. a plain text scene that is left becomes a list of its narration's own phrases.
    Every candidate passes the same checks as an AI pick: validation, numbers from facts or the narration,
    grounded text, no repeats, at most two 3D and never two 3D in a row. Returns notes for the log."""
    if ctx.brief.mode != "og":
        return []
    rng = random.Random(f"variety-{ctx.job.id}")
    text = {s.segment_id: s.text for s in script.segments}
    numbers = _numbers_in_facts(facts)
    grounding = None if ctx.brief.content_type == "fictional_story" else grounding_corpus(ctx, script, facts)
    topic = topic_text(ctx, script)
    # a topic animation or a layout that claims a structure (a loop, layers, causes) is only added when the
    # topic clearly calls for it; the neutral list layouts fit anything
    fits = template_catalog.fits(topic, min_hits=2)
    strong = [n for n in template_catalog.suggest(topic, weights, k=12, seed=ctx.job.id)
              if template_catalog.topical(n) and template_catalog._hits(template_catalog.BY_NAME[n], topic) >= 2]
    scenes = sb.scenes
    middle = [i for i, sc in enumerate(scenes) if sc.visual_type not in ("title", "end_card")]
    tpl = lambda i: (scenes[i].manim_template or {}).get("template") if scenes[i].visual_type == "manim" else None  # noqa: E731
    jitter = {t: rng.random() * 0.05 for t in manim_runner.TEMPLATES}
    # lower is better: recently used and generic templates cost more, a topic animation that fits costs less
    cost = lambda t: (weights.get(t, 0.0) + (1.5 if t in template_catalog.GENERIC else 0.0) + jitter[t]  # noqa: E731
                      - (2.0 if template_catalog.topical(t) and t in fits else 0.0))
    lines = lambda i: [text.get(x, "") for x in scenes[i].segment_ids]  # noqa: E731

    def allowed(i: int, name: str, mt: dict) -> bool:
        others = [tpl(j) for j in range(len(scenes)) if j != i]
        if name in others:
            return False
        if name in manim_runner.THREE_D:
            if sum(1 for t in others if t in manim_runner.THREE_D) >= MAX_3D_SCENES:
                return False
            if any(0 <= j < len(scenes) and tpl(j) in manim_runner.THREE_D for j in (i - 1, i + 1)):
                return False
        try:
            check_manim(mt, numbers, grounding, " ".join(lines(i)))
        except (ValueError, ValidationError, TypeError):
            return False
        return True

    def best(i: int, options: dict[str, dict]) -> tuple[str, dict] | None:
        ok = [(cost(n), n, mt) for n, mt in options.items() if mt and allowed(i, n, mt)]
        return min(ok, key=lambda x: x[0])[1:] if ok else None

    def built(i: int, names) -> dict[str, dict]:
        sc = scenes[i]
        head = sc.visual_parameters.get("heading") or " ".join(sc.on_screen_text.split()[:5])
        items = [str(x) for x in sc.visual_parameters.get("points") or sc.visual_parameters.get("steps") or []] \
            or template_catalog.phrases(lines(i))
        return {n: template_catalog.build(n, head, items, topic, lines(i)) for n in names}

    def use(i: int, name: str, mt: dict, why: str) -> None:
        sc = scenes[i]
        sc.visual_type, sc.visual_parameters, sc.manim_template = "manim", {"heading": ""}, mt
        sc.template_reason = why

    notes = []
    # 1. the animation made for this topic, when the AI left it out
    if strong and not any(template_catalog.topical(tpl(i) or "") for i in middle):
        # plain text first, then the thinnest Remotion visual, then a general (non-topic) Manim scene
        order = sorted(middle, key=lambda i: (0 if scenes[i].visual_type == "text_reveal" else
                                              1 if not tpl(i) else 2 + (tpl(i) not in template_catalog.GENERIC)))
        for i in order:
            pick = best(i, built(i, strong[:3]))
            if pick:
                notes.append(f"scene {i + 1}: {tpl(i) or scenes[i].visual_type} -> {pick[0]} (made for this topic)")
                use(i, pick[0], pick[1], "topic: made for this kind of topic")
                break
    # 2. swap repeated or generic picks for a same-data template the user has seen less
    for i in middle:
        cur = tpl(i)
        if not cur or template_catalog.topical(cur) or not (cur in template_catalog.GENERIC
                                                            or weights.get(cur, 0) >= 1.0):
            continue
        # the same data in another template; a generic or very overused pick may also become another layout
        # of its narration's phrases
        alts = {**(built(i, sorted(fits | template_catalog.NEUTRAL))
                   if cur in template_catalog.GENERIC or weights.get(cur, 0) >= 2.0 else {}),
                **template_catalog.alternatives(cur, scenes[i].manim_template)}
        pick = best(i, {n: mt for n, mt in alts.items() if n != cur})
        if pick and cost(pick[0]) < cost(cur) - 0.3:
            use(i, pick[0], pick[1], f"variety: same data as {cur}")
            notes.append(f"scene {i + 1}: {cur} -> {pick[0]} (used less recently)")
    # 3. promote Remotion and text scenes until the video has enough Manim scenes
    candidates = sorted(fits | template_catalog.NEUTRAL)
    while sum(1 for i in middle if tpl(i)) < manim_target(len(middle)):
        found = []
        for i in middle:
            sc = scenes[i]
            if tpl(i):
                continue
            head = " ".join(sc.on_screen_text.split()[:4])[:30]
            if sc.visual_type in REMOTION_SOURCES:
                rank = REMOTION_SOURCES.index(sc.visual_type)
                params = {**sc.visual_parameters, "heading": sc.visual_parameters.get("heading") or head}
                options = template_catalog.alternatives("@" + sc.visual_type, params)
            elif sc.visual_type == "text_reveal":
                rank = len(REMOTION_SOURCES)
                options = template_catalog.narration_list(lines(i), head)
            else:
                continue
            # the visual's own data (a stat, chart, comparison) first; a layout of its phrases only if none fits
            pick = best(i, {k: v for k, v in options.items() if v}) or best(i, built(i, candidates))
            if pick:
                found.append((rank, cost(pick[0]), i, pick))
        if not found:
            break
        _, _, i, (name, mt) = min(found, key=lambda x: x[:2])
        notes.append(f"scene {i + 1}: {scenes[i].visual_type} -> {name} (more Manim scenes)")
        use(i, name, mt, f"variety: from {scenes[i].visual_type}")
    # 4. a text scene that is left shows its narration's key phrases instead of a wall of text
    for i in middle:
        sc = scenes[i]
        if sc.visual_type != "text_reveal":
            continue
        points = [p for p in template_catalog.phrases(lines(i), 5) if _grounded(p, grounding, " ".join(lines(i)))] \
            if grounding is not None else template_catalog.phrases(lines(i), 5)
        if len(points) >= 2:
            head = " ".join(sc.on_screen_text.split()[:6])
            sc.visual_type = "key_points"
            sc.visual_parameters = PARAM_MODELS["key_points"].model_validate(
                {"heading": head, "points": points[:5]}).model_dump()
            notes.append(f"scene {i + 1}: text_reveal -> key_points (its narration's phrases)")
    return notes


class _Repeat(Exception):
    """A valid Manim scene that breaks a per-video variety rule (repeat, too many 3D, 3D twice in a row)."""


def system_prompt(seed: int | str, exclude: set[str] | frozenset = frozenset()) -> str:
    """The storyboard prompt with the template catalog in a per-video order, so list position is no bias."""
    return SYSTEM.replace("{catalog}", template_catalog.catalog_text(seed, exclude))


def unusable_templates(ctx: AgentContext, facts: Facts, script: Script | None = None) -> set[str]:
    """Templates this video's sources cannot fill (no numbers, no quotation), see template_catalog.unusable."""
    sources = ""
    idx = ctx.job.path("retrieval_index.json")
    if idx.exists():
        import json
        sources = " ".join(c.get("text", "") for c in json.loads(idx.read_text(encoding="utf-8")))
    return template_catalog.unusable(_numbers_in_facts(facts), sources,
                                     " ".join(s.text for s in script.segments) if script else "")


def picker_hints(ctx: AgentContext, plan: Plan, script: Script,
                 skip: set[str] | frozenset = frozenset()) -> tuple[list[str], list[str]]:
    """(likely fits for this topic, templates the user's recent videos already used a lot)."""
    weights = template_catalog.recent_weights(ctx.job.dir.parent, exclude=ctx.job.id)
    topic = " ".join([ctx.brief.topic, script.title, *plan.manim_scenes, *(s.text for s in script.segments)])
    fits = template_catalog.suggest(topic, weights, k=6, seed=ctx.job.id, exclude=skip)
    # plus a few general templates the user has seen least, so every template comes up over a run of videos
    fits += [t for t in template_catalog.fresh(weights, skip | set(fits), k=3, seed=ctx.job.id)]
    return fits, [t for t, w in sorted(weights.items(), key=lambda x: -x[1])
                  if w >= 1.0 and not template_catalog.topical(t)][:8]


def log_picks(ctx: AgentContext, sb: StoryboardLLM, fits: list[str], avoid: list[str]) -> None:
    picks = [{"scene": i, "template": sc.manim_template.get("template"), "why": sc.template_reason[:80]}
             for i, sc in enumerate(sb.scenes, 1) if sc.visual_type == "manim" and sc.manim_template]
    ctx.job.log.log("storyboarding", "picker", "templates_chosen", templates=[p["template"] for p in picks],
                    picks=picks, suggested=fits, recently_used=avoid)


# ---------------- on-screen text grounding ----------------
URLISH = re.compile(r"(https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|in|org|net|io|ai|dev|co|me)(?:/\S*)?|"
                    r"\b[\w.+-]+@[\w-]+\.[\w.]+\b|\+?\d[\d\s-]{8,}\d)", re.I)
MAX_3D_SCENES = 2
LIST_FIELDS = ("points", "steps", "leftPoints", "rightPoints", "labels")


def grounding_corpus(ctx: AgentContext, script: Script, facts: Facts) -> dict:
    """Everything on-screen text may draw on: narration, supported facts, supplied sources and the brief."""
    parts = [s.text for s in script.segments] + [script.title, script.cta]
    parts += [f.claim + " " + f.evidence for f in facts.supported()]
    b = ctx.brief
    parts += [b.topic, b.audience, b.cta, *b.must_include]
    idx = ctx.job.path("retrieval_index.json")
    if idx.exists():
        import json
        parts += [c.get("text", "") for c in json.loads(idx.read_text(encoding="utf-8"))]
    raw = " ".join(p for p in parts if p)
    return {"text": raw.lower(), "tokens": set(tokenize(raw)), "numbers": raw.replace(",", "")}


def _grounded(item: str, g: dict, scene_text: str) -> bool:
    nums = re.findall(r"\d+(?:\.\d+)?", item.replace(",", ""))
    if any(n not in g["numbers"] for n in nums):
        return False
    toks = set(tokenize(item))
    if not toks:
        return True
    known = g["tokens"] | set(tokenize(scene_text))
    if len(toks) <= 3:  # short labels ("Scikit-learn", "TensorFlow/PyTorch") must be fully supported
        return toks <= known
    return len(toks & known) / len(toks) >= 0.5


def _strings(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def check_general_text(mt: dict, g: dict, scene_text: str) -> None:
    """The general Manim templates show free text, so it gets the same source check as other on-screen text:
    numbers (years, counts) must appear in the sources, and a quotation must be one the sources or narration
    actually contain, with a speaker they name. Raises ValueError so the scene falls back to a safe visual."""
    skip = {"template", "look", "mode", "style", "verdict", "palette"}
    for k, v in mt.items():
        if k in skip or k in manim_runner.NUMBER_FIELDS.get(mt.get("template"), ()):
            continue
        for s in _strings(v):
            nums = re.findall(r"\d+(?:\.\d+)?", s.replace(",", ""))
            bad = [n for n in nums if n not in g["numbers"] and n not in scene_text.replace(",", "")]
            if bad:
                raise ValueError(f"{k!r} shows numbers not found in the sources: {bad}")
    if mt.get("template") == "quote_card":
        toks = set(tokenize(str(mt.get("quote", ""))))
        known = g["tokens"] | set(tokenize(scene_text))
        if toks and len(toks & known) / len(toks) < 0.85:
            raise ValueError("the quote is not in the sources or narration")
        who = set(tokenize(str(mt.get("author", ""))))
        if who and not who <= known:
            raise ValueError("the quote's speaker is not named in the sources")


def _strip_urls(s: str, g: dict) -> tuple[str, bool]:
    changed = False

    def repl(m):
        nonlocal changed
        if m.group(0).lower() in g["text"]:
            return m.group(0)
        changed = True
        return ""
    out = re.sub(r"\s{2,}", " ", URLISH.sub(repl, s)).strip(" -:,")
    return out, changed


def ground_params(vt: str, params: dict, g: dict, scene_text: str, cta: str) -> tuple[dict, list[str]]:
    """Remove on-screen text the sources do not support: invented URLs/emails/phone numbers, numbers that no
    supported fact contains, and list items with no basis in the narration or sources."""
    notes: list[str] = []
    p = dict(params)
    for k, v in list(p.items()):
        if isinstance(v, str):
            new, changed = _strip_urls(v, g)
            if changed:
                notes.append(f"removed an unsupported link/contact from {k!r}")
                if k == "cta" and cta and len(new.split()) < 2:
                    p[k] = cta  # the user's own CTA from the brief needs no source support
                    continue
            if k in ("value",):
                continue
            if new and not _grounded(new, g, scene_text) and k in ("label", "subtitle", "cta", "text"):
                notes.append(f"dropped unsupported {k!r}: {new[:60]!r}")
                new = "" if k != "text" else scene_text
            p[k] = new
        elif k in LIST_FIELDS and isinstance(v, list) and k != "labels":
            keep = []
            for item in v:
                s, _ = _strip_urls(str(item), g)
                if s and _grounded(s, g, scene_text):
                    keep.append(s)
                else:
                    notes.append(f"dropped unsupported {k[:-1]} {str(item)[:60]!r}")
            p[k] = keep
        elif k == "events" and isinstance(v, list):
            kept = [e for e in v if isinstance(e, dict)
                    and _grounded(f"{e.get('label', '')} {e.get('detail', '')}", g, scene_text)]
            if len(kept) < len(v):
                notes.append(f"dropped {len(v) - len(kept)} unsupported timeline event(s)")
            p[k] = kept
    return p, notes


def fix_coverage(sb: StoryboardLLM, script: Script) -> StoryboardLLM:
    """Force every segment to appear exactly once, in order."""
    order = [s.segment_id for s in script.segments]
    seen, scenes = set(), []
    for sc in sb.scenes:
        ids = [i for i in sc.segment_ids if i in order and i not in seen]
        if not ids:
            continue
        seen.update(ids)
        sc.segment_ids = sorted(ids, key=order.index)
        scenes.append(sc)
    scenes.sort(key=lambda s: order.index(s.segment_ids[0]))
    missing = [i for i in order if i not in seen]
    for m in missing:  # attach to the scene that precedes it in script order
        idx = order.index(m)
        host = max((s for s in scenes if order.index(s.segment_ids[0]) < idx),
                   key=lambda s: order.index(s.segment_ids[0]), default=scenes[0] if scenes else None)
        if host is None:
            scenes.append(SceneLLM(segment_ids=[m], visual_type="text_reveal", visual_parameters={"text": m}))
        else:
            host.segment_ids = sorted(host.segment_ids + [m], key=order.index)
    # contiguity: a scene's segments must be consecutive; split otherwise
    out = []
    for sc in scenes:
        run = [sc.segment_ids[0]]
        for i in sc.segment_ids[1:]:
            if order.index(i) == order.index(run[-1]) + 1:
                run.append(i)
            else:
                out.append(sc.model_copy(update={"segment_ids": run}))
                run = [i]
        out.append(sc.model_copy(update={"segment_ids": run}))
    out.sort(key=lambda s: order.index(s.segment_ids[0]))
    return StoryboardLLM(scenes=out)


def to_storyboard(ctx: AgentContext, sb: StoryboardLLM, script: Script, origin: str) -> Storyboard:
    wps = script.words_per_minute / 60
    words = {s.segment_id: len(s.text.split()) for s in script.segments}
    seg_fact = {s.segment_id: s.fact_ids for s in script.segments}
    total_est = sum(words.values()) / wps
    scale = ctx.brief.duration_s / total_est if total_est else 1
    t = 0.0
    scenes = []
    for i, sc in enumerate(sb.scenes, 1):
        dur = max(0.5, sum(words[x] for x in sc.segment_ids) / wps * scale)
        refs = sorted({f for x in sc.segment_ids for f in seg_fact.get(x, [])})
        assets = []
        if sc.visual_type == "manim":
            assets.append(f"manim:S{i:02d}")
        if sc.visual_type == "gameplay":
            assets.append(f"gameplay:{ctx.brief.mode}")
        scenes.append(StoryboardScene(scene_id=f"S{i:02d}", start_time=round(t, 3), duration=round(dur, 3),
                                      narration_segment_ids=sc.segment_ids, on_screen_text=sc.on_screen_text,
                                      visual_type=sc.visual_type, visual_parameters=sc.visual_parameters,
                                      asset_references=assets, transition=sc.transition,  # type: ignore[arg-type]
                                      backdrop=sc.backdrop if sc.backdrop in BACKDROP_STYLES else "",
                                      source_references=refs, manim_template=sc.manim_template))
        t = round(t + dur, 3)
    return Storyboard(mode=ctx.brief.mode, scenes=scenes, origin=origin)  # type: ignore[arg-type]


def run(ctx: AgentContext, plan: Plan, script: Script, facts: Facts) -> Storyboard:
    origin = "local"
    data = None
    skip = unusable_templates(ctx, facts, script) if ctx.brief.mode == "og" else set()
    fits, avoid = picker_hints(ctx, plan, script, skip) if ctx.brief.mode == "og" else ([], [])
    if ctx.brief.mode == "og":
        segs = "\n".join(f"{s.segment_id} [{s.beat}] {s.text} (facts: {s.fact_ids})" for s in script.segments)
        sup = "\n".join(f"{f.fact_id}: {f.claim} (source: {f.source}, p.{f.page})" for f in facts.supported()) \
            or "(none: do not use stat or chart)"
        user = (f"Title: {script.title}\nAudience: {ctx.brief.audience}\nTarget scenes: about {plan.scene_count}\n"
                f"Beats the planner thought suit Manim (ideas, not limits): {plan.manim_scenes}\n"
                f"Templates that may fit this topic, best first, then a few this user has not seen lately: "
                f"{', '.join(fits) or '(none stand out; read the catalog)'}\n"
                f"Used a lot in this user's recent videos, so pick something else unless it clearly fits best: "
                f"{', '.join(avoid) or '(none)'}\nCTA: {script.cta}\n\nSegments:\n{segs}\n\n"
                f"Supported facts (numbers on screen come from these or from the scene's own narration):\n{sup}")
        data = ask_llm(ctx, "storyboarding", system_prompt(ctx.job.id, skip), user, StoryboardLLM, PROMPT_VERSION, temperature=0.4,
                       max_tokens=3000)
        if data:
            origin = "llm"
    data = data or local_storyboard(ctx, plan, script, facts, fits)
    data = fix_coverage(data, script)
    data, notes = sanitize(ctx, data, script, facts)
    for n in notes:
        ctx.job.log.log("storyboarding", "validator", "repaired", note=n)
    if ctx.brief.mode == "og":
        ai_picks = [sc.manim_template.get("template") for sc in data.scenes
                    if sc.visual_type == "manim" and sc.manim_template]
        changes = diversify(ctx, data, script, facts,
                            template_catalog.recent_weights(ctx.job.dir.parent, exclude=ctx.job.id))
        if changes:
            ctx.job.log.log("storyboarding", "picker", "variety", ai_picks=ai_picks, changes=changes)
        log_picks(ctx, data, fits, avoid)
    if ctx.brief.mode != "og":
        if attach_motion(ctx, data, script):
            origin = "llm"
    sb = to_storyboard(ctx, data, script, origin)
    issues = sb.validate_against(script, ctx.brief.duration_s, tol=0.05)
    if issues:
        ctx.job.log.log("storyboarding", "validator", "issues", issues=issues)
    return sb



def from_user(ctx: AgentContext, data: dict, script: Script, facts: Facts) -> Storyboard:
    """A storyboard supplied by the user: {"scenes": [{"segment_ids": [...], "visual_type": ..., ...}]}.
    It gets exactly the same coverage, parameter, number and Manim validation as an LLM storyboard."""
    sb = StoryboardLLM.model_validate(data)
    sb = fix_coverage(sb, script)
    sb, notes = sanitize(ctx, sb, script, facts)
    for n in notes:
        ctx.job.log.log("storyboarding", "validator", "repaired", note=n, source="user storyboard")
    if ctx.brief.mode != "og":
        attach_motion(ctx, sb, script, use_llm=False)
    return to_storyboard(ctx, sb, script, "user")


# ---------------- brainrot motion cues ----------------
MOTION_LEVELS = {"calm": 0, "normal": 1, "strong": 2, "hit": 3}
MOTION_SYSTEM = """You are the Storyboarder for a fast short-form video over gameplay footage. For each narration
line choose how hard the camera should react when its caption appears:
- calm: no camera reaction (reflective or quiet lines)
- normal: no camera reaction, the default for most lines
- strong: a punch-in with a small shake (a key point or surprising fact)
- hit: the biggest punch and shake (the hook, a twist, the punchline)
Most lines should be normal or calm. Use strong for at most a quarter of the lines and hit at most twice;
reacting on every line feels like a glitch. Return ONLY JSON: {"lines": [{"segment_id": "N01", "motion": "hit"}]}"""


class MotionLine(BaseModel):
    segment_id: str
    motion: str


class MotionLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    lines: list[MotionLine] = Field(default_factory=list)


def rule_motion(script: Script) -> dict[str, str]:
    """Fallback when no model is available: hook and questions/exclamations hit hardest, last line calms down."""
    out = {}
    segs = script.segments
    for i, s in enumerate(segs):
        t = s.text.strip()
        if i == 0:
            out[s.segment_id] = "hit"
        elif t.endswith(("!", "?")) and i < len(segs) - 1:
            out[s.segment_id] = "strong"
        else:
            out[s.segment_id] = "normal"
    if segs and len(segs) > 2:
        out[segs[-1].segment_id] = "calm"
    return out


def attach_motion(ctx: AgentContext, sb: StoryboardLLM, script: Script, use_llm: bool = True) -> bool:
    """Store a motion level per narration line in each gameplay scene. Returns True if the model chose them."""
    levels, by_model = None, False
    if use_llm:
        lines = "\n".join(f"{s.segment_id} [{s.beat}] {s.text}" for s in script.segments)
        data = ask_llm(ctx, "storyboarding", MOTION_SYSTEM, f"Tone: {ctx.brief.tone}\n\nLines:\n{lines}", MotionLLM,
                       "storyboarder/motion-v2", temperature=0.3, max_tokens=1200)
        if data:
            picked = {ln.segment_id: ln.motion.strip().lower() for ln in data.lines
                      if ln.motion.strip().lower() in MOTION_LEVELS}
            if picked:
                levels, by_model = {**rule_motion(script), **picked}, True
    levels = levels or rule_motion(script)
    for sc in sb.scenes:
        sc.visual_parameters = {**sc.visual_parameters,
                                "motion": {sid: levels.get(sid, "normal") for sid in sc.segment_ids}}
    ctx.job.log.log("storyboarding", "motion", "ok", chosen_by="model" if by_model else "rule", levels=levels)
    return by_model
