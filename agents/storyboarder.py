"""Agent 4: Storyboarder -> storyboard.json

The storyboard only *describes* scenes with parameters for trusted renderers.
It never contains code. Planned times are estimates from the word count; the
Editor later replaces them with measured narration timings.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.base import AgentContext, ask_llm
from core.mathtext import clean_tree, latex_to_unicode
from retrieval.index import tokenize
from rendering import manim_runner
from schemas.artifacts import Facts, Plan, Script, Storyboard, StoryboardScene
from schemas.render_props import BACKDROP_STYLES, PARAM_MODELS, VISUAL_TYPES_OG

PROMPT_VERSION = "storyboarder/v6"

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
- manim: a Manim diagram; set visual_parameters {"heading": str} and manim_template to one of
    {"template": "process_diagram", "title": str, "steps": [2-6 strings]}
    {"template": "flow_diagram", "title": str, "inputs": [..], "center": str, "outputs": [..]}
    {"template": "timeline", "title": str, "events": [{"label": str, "detail": str}]}
    {"template": "simple_chart", "title": str, "labels": [..], "values": [numbers], "unit": str}
    {"template": "equation_steps", "title": str, "lines": [2-6 equations, each the whole equation after one step,
      plain text like "x^2 + 2x = 8"], "notes": [one short note per step after the first line, e.g. "subtract 3"]}
    Put a whole worked problem in ONE equation_steps scene rather than one scene per step.
    {"template": "chemical_reaction", "title": str, "reactants": ["2H2", "O2"], "products": ["2H2O"],
      "condition": "spark"}  (formulas only; digits become subscripts)
    {"template": "array_algorithm", "title": str, "algorithm": "bubble_sort|selection_sort|insertion_sort|
      linear_search|binary_search", "values": [3-8 small whole numbers], "target": number (searches only)}
      (the animation runs the real algorithm on the values, step by step)
    {"template": "agent_loop", "title": str, "goal": str, "agent": str, "steps": ["Plan", "Act", "Observe", ...],
      "tools": [0-4 tool names], "result": str}
    {"template": "security_flow", "title": str, "attacker": str, "attack": str, "defense": str, "target": str,
      "outcome": "blocked|breached", "encrypted": true|false}
    {"template": "function_plot", "title": str, "functions": [{"expr": "x^2 - 4", "label": ""}] (1-3, plain math
      in x: + - * / ^, sin cos tan exp log sqrt abs, pi, e), "x_min": -5, "x_max": 5, "mark_x": [roots/peaks]}
    {"template": "line_chart", "title": str, "labels": [2-10 x labels], "series": [{"name": str, "values": [..]}]
      (1-3 series, one value per label, ONLY numbers from supported facts), "unit": str}
    {"template": "pie_chart", "title": str, "labels": [2-6], "values": [..] (ONLY supported numbers), "unit": "%"}
    {"template": "node_graph", "title": str, "nodes": [2-10 short names], "edges": [["A", "B"], ...],
      "path": [node names in visit order], "directed": bool, "layers": [3, 4, 2] (only for neural networks)}
    {"template": "cycle_diagram", "title": str, "stages": [3-6 stages in order], "center": str}
    {"template": "venn_diagram", "title": str, "sets": [{"name": str, "items": [0-3]}] (2-3 sets), "shared": [0-3]}
    {"template": "pyramid", "title": str, "levels": [2-6, top level first]}
    {"template": "mind_map", "title": str, "center": str, "branches": [{"name": str, "items": [0-2]}] (2-6)}
  Use cycle_diagram for anything that repeats in a loop (water cycle, life cycles, feedback loops),
  venn_diagram to compare 2-3 things and what they share, pyramid for hierarchies and levels (Maslow, food
  chains, OSI layers), mind_map for an overview of a topic's main parts. Prefer variety: do not use the same
  Manim template twice in one video when another one fits.
  Use function_plot for graphs of functions (parabolas, growth, trigonometry), line_chart for trends over time,
  pie_chart for shares of a whole, node_graph for networks, graph algorithms (BFS, DFS, shortest path),
  routing, social or neural networks.
  Use equation_steps whenever the narration works through math (solving, simplifying, a formula),
  chemical_reaction whenever it describes a reaction, array_algorithm for sorting or searching algorithms,
  agent_loop for AI agents / agentic workflows / tool use, and security_flow for attacks, malware, phishing,
  firewalls or encryption. Only show equations, formulas and names the narration states.
- end_card: {"text": str, "cta": str}
Give each scene a "backdrop" (animated background). Match the mood: grid (technical, data), waves (calm,
flowing), rays (big reveal, title), shapes (playful), orbs (neutral), aurora (dreamy, nature, space),
constellation (networks, AI, connections), hexgrid (science, chemistry, structure), circuit (computing,
electronics, software), contours (geography, physics, maps), stripes (energetic, fast facts), matrix (code,
hacking, cybersecurity). Use a variety across the video and avoid
using the same backdrop twice in a row.
Use the first scene as a title and the last as an end_card. Every segment id must be used exactly once, in order.
Keep on-screen text short (under 8 words per item). Return ONLY JSON:
{"scenes": [{"segment_ids": [...], "visual_type": "...", "visual_parameters": {...}, "on_screen_text": "",
 "transition": "fade|slide|zoom", "backdrop": "grid", "manim_template": null}]}"""


class SceneLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    segment_ids: list[str] = Field(default_factory=list)  # empty scenes are dropped by fix_coverage
    visual_type: str
    visual_parameters: dict = Field(default_factory=dict)
    on_screen_text: str = ""
    transition: str = "fade"
    backdrop: str = ""
    manim_template: dict | None = None


class StoryboardLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    scenes: list[SceneLLM] = Field(min_length=1, max_length=14)


def shorten(text: str, n: int = 8) -> str:
    words = re.sub(r"[.!?]+$", "", text.strip()).split()
    s = " ".join(words[:n])
    return s + ("â€¦" if len(words) > n else "")


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


def local_storyboard(ctx: AgentContext, plan: Plan, script: Script, facts: Facts) -> StoryboardLLM:
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
                                   manim_template={"template": "process_diagram", "title": shorten(
                                       plan.manim_scenes[0].capitalize(), 6), "steps": steps}))
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
    for sc in sb.scenes:
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
            if not vals or any(v is None or f"{float(v):g}" not in numbers for v in vals if v is not None):
                notes.append(f"{sc.visual_type} scene used numbers not found in supported facts; replaced")
                sc.visual_type, sc.visual_parameters = "text_reveal", fallback
                continue
        if sc.visual_type == "manim":
            try:
                if not sc.manim_template:
                    raise ValueError("missing manim_template")
                tpl = sc.manim_template.get("template")
                if tpl in ("simple_chart", "pie_chart", "line_chart"):
                    vals = sc.manim_template.get("values", []) if tpl != "line_chart" else \
                        [v for s in sc.manim_template.get("series", []) for v in (s.get("values") or [])]
                    if any(f"{float(v):g}" not in numbers for v in vals):
                        raise ValueError("chart values are not in supported facts")
                manim_runner.validate(sc.manim_template)
            except (ValueError, ValidationError, TypeError) as e:
                notes.append(f"invalid Manim template replaced with a Remotion process/text scene: {e}")
                steps = (sc.manim_template or {}).get("steps") or []
                if 2 <= len(steps) <= 6:
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


# ---------------- on-screen text grounding ----------------
URLISH = re.compile(r"(https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|in|org|net|io|ai|dev|co|me)(?:/\S*)?|"
                    r"\b[\w.+-]+@[\w-]+\.[\w.]+\b|\+?\d[\d\s-]{8,}\d)", re.I)
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
    if ctx.brief.mode == "og":
        segs = "\n".join(f"{s.segment_id} [{s.beat}] {s.text} (facts: {s.fact_ids})" for s in script.segments)
        sup = "\n".join(f"{f.fact_id}: {f.claim} (source: {f.source}, p.{f.page})" for f in facts.supported()) \
            or "(none: do not use stat or chart)"
        user = (f"Title: {script.title}\nAudience: {ctx.brief.audience}\nTarget scenes: about {plan.scene_count}\n"
                f"Manim-worthy beats: {plan.manim_scenes}\nCTA: {script.cta}\n\nSegments:\n{segs}\n\n"
                f"Supported facts (the only allowed source of numbers):\n{sup}")
        data = ask_llm(ctx, "storyboarding", SYSTEM, user, StoryboardLLM, PROMPT_VERSION, temperature=0.4,
                       max_tokens=3000)
        if data:
            origin = "llm"
    data = data or local_storyboard(ctx, plan, script, facts)
    data = fix_coverage(data, script)
    data, notes = sanitize(ctx, data, script, facts)
    for n in notes:
        ctx.job.log.log("storyboarding", "validator", "repaired", note=n)
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
