"""The Manim template catalog the Storyboarder chooses from.

One entry per template: its group, a one-line "use when", the fields it takes and a few topic keywords.
The storyboard prompt is generated from this list (in a per-video shuffled order, so the first few
entries do not win every time), the keywords rank likely fits for a topic, and recent videos' picks
are read back from outputs/ so the same templates are not reused video after video.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rendering import manim_runner


@dataclass(frozen=True)
class Entry:
    name: str
    group: str
    use_when: str
    fields: str
    keywords: tuple[str, ...] = ()

    @property
    def is_3d(self) -> bool:
        return self.name in manim_runner.THREE_D


# generic fallbacks: fine for anything, so they are only used when nothing specific fits
GENERIC = {"process_diagram", "flow_diagram"}

CATALOG: tuple[Entry, ...] = (
    # ---- steps and flow
    Entry("process_diagram", "steps", "a plain sequence of steps, only when no more specific template fits",
          '"title": str, "steps": [2-6 strings]'),
    Entry("flow_diagram", "steps", "inputs going into one thing and outputs coming out, only when nothing "
          "more specific fits", '"title": str, "inputs": [..], "center": str, "outputs": [..]'),
    Entry("cycle_diagram", "steps", "anything that repeats in a loop (water cycle, life cycles, feedback loops)",
          '"title": str, "stages": [3-6 stages in order], "center": str',
          ("cycle", "loop", "repeat", "feedback", "life cycle", "water", "season", "habit", "recycle")),
    Entry("roadmap", "steps", "a journey, plan or learning path toward a goal",
          '"title": str, "stops": [2-6 steps of a journey or plan, first first], "goal": str',
          ("roadmap", "journey", "path", "plan", "learning path", "career", "beginner", "guide", "become")),
    Entry("domino_chain", "steps", "a chain of causes and consequences ending in one effect",
          '"title": str, "links": [2-6 causes in order], "effect": str',
          ("cause", "effect", "led to", "chain", "collapse", "crisis", "because", "consequence", "fall",
           "inflation", "war", "crash")),
    Entry("decision_tree", "steps", "a choice between options and what each leads to",
          '"title": str, "question": str, "options": [{"choice": str, "outcome": str}] (2-3), '
          '"picked": index of the option the narration recommends, or null',
          ("choose", "choice", "decide", "decision", "should you", "option", "which one")),
    Entry("timeline", "steps", "a short dated history (2-6 events)",
          '"title": str, "events": [{"label": str, "detail": str}]',
          ("history", "year", "century", "founded", "invented", "era", "timeline")),
    # ---- comparison and lists
    Entry("before_after", "compare", "two options side by side, or a change from before to after",
          '"title": str, "mode": "versus|before_after", "left_title": str, "right_title": str, '
          '"left_points": [0-4], "right_points": [0-4], "verdict": str',
          ("vs", "versus", "compare", "difference", "before", "after", "old", "new", "better")),
    Entry("pros_cons", "compare", "advantages against disadvantages",
          '"title": str, "pros": [1-4], "cons": [1-4], "verdict": "pros|cons|even", '
          '"pros_label": "Pros", "cons_label": "Cons"',
          ("pros", "cons", "advantage", "disadvantage", "benefit", "risk", "worth", "downside", "trade")),
    Entry("venn_diagram", "compare", "2-3 things and what they share",
          '"title": str, "sets": [{"name": str, "items": [0-3]}] (2-3 sets), "shared": [0-3]',
          ("overlap", "both", "share", "in common", "similar", "difference between")),
    Entry("myth_fact", "compare", "common misconceptions and the truth",
          '"title": str, "pairs": [{"myth": str, "fact": str}] (1-3)',
          ("myth", "misconception", "actually", "truth", "wrong", "believe", "lie", "fake")),
    Entry("ranking", "lists", "top-N lists and leaders",
          '"title": str, "items": [2-6, first is number one], "values": [] or one supported number per item, '
          '"unit": str', ("top", "best", "biggest", "largest", "most", "rank", "richest", "fastest", "list")),
    Entry("spotlight", "lists", "picking the one key factor out of several",
          '"title": str, "words": [3-8 short words or phrases], "focus": "the key one of the words", "caption": str',
          ("key factor", "secret", "most important", "factor", "one thing", "real reason")),
    Entry("pyramid", "lists", "hierarchies and levels (Maslow, food chains, OSI layers)",
          '"title": str, "levels": [2-6, top level first]',
          ("hierarchy", "level", "pyramid", "maslow", "food chain", "needs", "tier")),
    Entry("mind_map", "lists", "an overview of a topic's main parts",
          '"title": str, "center": str, "branches": [{"name": str, "items": [0-2]}] (2-6)',
          ("overview", "types", "parts", "branches", "kinds", "areas", "everything about")),
    Entry("funnel", "lists", "narrowing stages (sales, hiring, filtering, selection)",
          '"title": str, "stages": [2-5, widest first], "values": [] or one supported number per stage, "unit": str',
          ("funnel", "sales", "hiring", "filter", "conversion", "leads", "applicants", "marketing")),
    Entry("quote_card", "lists", "a quotation, only when the sources contain it",
          '"title": str, "quote": str (ONLY words quoted in the sources), "author": str, '
          '"highlight": "a word from the quote"', ("said", "quote", "speech", "famous words")),
    # ---- numbers and data (ONLY supported numbers)
    Entry("stat_reveal", "data", "one striking supported number",
          '"title": str, "value": number (ONLY a supported number), "prefix": str, "suffix": str, "label": str, '
          '"style": "counter|ring|dots" (ring and dots only for a percentage, suffix "%")',
          ("percent", "%", "million", "billion", "statistic", "record")),
    Entry("simple_chart", "data", "a bar chart of a few supported numbers",
          '"title": str, "labels": [..], "values": [numbers], "unit": str', ("chart", "compare numbers")),
    Entry("line_chart", "data", "a trend over time from supported numbers",
          '"title": str, "labels": [2-10 x labels], "series": [{"name": str, "values": [..]}] (1-3 series, '
          'one value per label, ONLY numbers from supported facts), "unit": str',
          ("trend", "growth", "over time", "rise", "decline", "price", "population")),
    Entry("pie_chart", "data", "shares of a whole",
          '"title": str, "labels": [2-6], "values": [..] (ONLY supported numbers), "unit": "%"',
          ("share", "percent of", "breakdown", "market share", "split")),
    # ---- maths, science and tech
    Entry("equation_steps", "science", "the narration works through math (solving, simplifying, a formula); "
          "put a whole worked problem in ONE scene",
          '"title": str, "lines": [2-6 equations, each the whole equation after one step, plain text like '
          '"x^2 + 2x = 8"], "notes": [one short note per step after the first line, e.g. "subtract 3"]',
          ("equation", "solve", "formula", "algebra", "theorem", "calculate", "math", "probability")),
    Entry("function_plot", "science", "graphs of functions (parabolas, growth, trigonometry)",
          '"title": str, "functions": [{"expr": "x^2 - 4", "label": ""}] (1-3, plain math in x: + - * / ^, '
          'sin cos tan exp log sqrt abs, pi, e), "x_min": -5, "x_max": 5, "mark_x": [roots/peaks]',
          ("graph", "function", "parabola", "exponential", "sine", "curve", "calculus", "derivative")),
    Entry("chemical_reaction", "science", "a chemical reaction (formulas only; digits become subscripts)",
          '"title": str, "reactants": ["2H2", "O2"], "products": ["2H2O"], "condition": "spark"',
          ("reaction", "chemistry", "chemical", "combust", "acid", "oxidation", "oxidis", "oxidiz", "photosynthesis")),
    Entry("array_algorithm", "tech", "sorting or searching algorithms (runs the real algorithm on the values)",
          '"title": "Example: ...", "algorithm": "bubble_sort|selection_sort|insertion_sort|quick_sort|'
          'linear_search|binary_search", "values": [3-8 small whole numbers, an example], '
          '"target": number (searches only)',
          ("sort", "search", "algorithm", "array", "binary search", "pivot", "partition")),
    Entry("node_graph", "tech", "networks, graph algorithms (BFS, DFS, shortest path), routing, social networks",
          '"title": str, "nodes": [2-10 short names], "edges": [["A", "B"], ...], "path": [node names in visit '
          'order], "directed": bool, "layers": [3, 4, 2] (only for neural networks)',
          ("network", "graph", "node", "route", "path", "connect", "bfs", "dfs", "dijkstra", "social")),
    Entry("agent_loop", "tech", "AI agents, agentic workflows and tool use",
          '"title": str, "goal": str, "agent": str, "steps": ["Plan", "Act", "Observe", ...], '
          '"tools": [0-4 tool names], "result": str', ("agent", "agentic", "llm", "tool use", "autonomous")),
    Entry("security_flow", "tech", "attacks, malware, phishing, firewalls or encryption",
          '"title": str, "attacker": str, "attack": str, "defense": str, "target": str, '
          '"outcome": "blocked|breached", "encrypted": true|false',
          ("hack", "attack", "malware", "phishing", "firewall", "encrypt", "password", "cyber", "security")),
    # ---- 3D (at most two per video, never two in a row)
    Entry("orbit_3d", "3d", "atoms, electrons, nuclear physics, planets and orbits",
          '"title": str, "kind": "atom|planets", "center": str, "orbiters": [1-6 names]',
          ("atom", "electron", "orbit", "planet", "solar system", "nuclear", "moon")),
    Entry("surface_3d", "3d", "multivariable functions, landscapes, potential wells, optimisation",
          '"title": str, "surface": "paraboloid|saddle|ripple|gaussian|waves|cone", "caption": str',
          ("gradient", "optimi", "surface", "landscape", "loss", "multivariable")),
    Entry("bar_chart_3d", "3d", "a dramatic comparison of a few supported numbers",
          '"title": str, "labels": [2-8], "values": [..] (ONLY supported numbers), "unit": str',
          ("compare", "biggest", "largest", "gdp", "revenue")),
    Entry("dna_helix_3d", "3d", "DNA, genes and heredity", '"title": str, "caption": str',
          ("dna", "gene", "heredity", "genetic", "crispr", "chromosome")),
    Entry("molecule_3d", "3d", "a named molecule",
          '"title": str, "molecule": "water|carbon_dioxide|methane|ammonia|ethylene|benzene|oxygen|ethanol", '
          '"caption": str', ("molecule", "water", "carbon dioxide", "methane", "benzene", "ethanol", "bond")),
    Entry("globe_3d", "3d", "global networks, trade, travel or the internet",
          '"title": str, "hubs": [2-6 places or nodes], "caption": str',
          ("global", "world", "internet", "trade", "travel", "countries", "shipping", "earth")),
    Entry("vector_field_3d", "3d", "electric, magnetic or flow fields",
          '"title": str, "field": "source|sink|vortex|uniform|dipole|helix", "caption": str',
          ("field", "magnet", "electric", "flow", "wind", "current")),
    Entry("crystal_lattice_3d", "3d", "crystals, metals and solids",
          '"title": str, "lattice": "simple_cubic|body_centered|face_centered|salt", "caption": str',
          ("crystal", "metal", "lattice", "salt", "diamond", "solid")),
    Entry("neural_net_3d", "3d", "neural networks and deep learning",
          '"title": str, "layers": [2-5 layer names, input first], "caption": str',
          ("neural", "deep learning", "machine learning", "ai model", "neuron", "transformer")),
    Entry("layer_stack_3d", "3d", "layered architectures (tech stacks, network layers)",
          '"title": str, "layers": [2-6, top layer first], "caption": str',
          ("stack", "layer", "architecture", "osi", "protocol", "frontend", "backend")),
    Entry("planet_layers_3d", "3d", "anything in nested shells (Earth's interior, atmosphere, a cell)",
          '"title": str, "layers": [2-5, innermost first], "caption": str',
          ("core", "mantle", "crust", "atmosphere", "shell", "cell", "interior")),
    Entry("wave_3d", "3d", "light, sound and waves",
          '"title": str, "kind": "electromagnetic|transverse|standing|longitudinal", "caption": str',
          ("wave", "light", "sound", "frequency", "radio", "vibration")),
    Entry("solids_3d", "3d", "geometry of 3D shapes",
          '"title": str, "shapes": [1-4 of cube|tetrahedron|octahedron|dodecahedron|icosahedron|sphere|'
          'cylinder|cone|torus]', ("shape", "geometry", "cube", "sphere", "volume", "polyhedr")),
    Entry("galaxy_3d", "3d", "galaxies and the universe", '"title": str, "arms": 2-4, "caption": str',
          ("galaxy", "universe", "milky way", "star", "cosmos", "black hole", "space")),
    Entry("carousel_3d", "3d", "a list of items or tips", '"title": str, "items": [3-6 short items], "caption": str',
          ("tips", "ways", "habits", "ideas", "things", "reasons")),
    Entry("podium_3d", "3d", "the top three", '"title": str, "places": [2-3, first place first], "caption": str',
          ("top 3", "top three", "winner", "best", "champion", "gold")),
    Entry("cube_faces_3d", "3d", "the sides or aspects of one idea",
          '"title": str, "faces": [2-5 sides or aspects of one idea], "caption": str',
          ("aspects", "sides", "pillars", "dimensions", "elements")),
    Entry("spiral_timeline_3d", "3d", "history and long timelines",
          '"title": str, "events": [2-6, earliest first], "caption": str',
          ("history", "evolution", "ancient", "centuries", "origin", "timeline")),
)

BY_NAME = {e.name: e for e in CATALOG}
GROUP_TITLES = {"steps": "Steps, causes and choices", "compare": "Comparisons", "lists": "Lists and ideas",
                "data": "Numbers (ONLY supported numbers)", "science": "Maths and science",
                "tech": "Computing and security", "3d": "3D (rotate in space)"}


# templates that show nothing without numbers (or a quotation) from the sources
NEEDS_NUMBERS = {"stat_reveal", "simple_chart", "line_chart", "pie_chart", "bar_chart_3d"}
NEEDS_QUOTE = {"quote_card"}


def unusable(fact_text: str, source_text: str, narration: str = "") -> set[str]:
    """Templates this video's sources cannot fill: with no digits in any supported fact or in the (fact-checked)
    narration, a chart or big number would have to be invented (the validator would drop it), and with no
    quotation marks there is no quote."""
    out = set()
    if not re.search(r"\d", fact_text + " " + narration):
        out |= NEEDS_NUMBERS
    if not re.search(r"[\"“”]", fact_text + " " + source_text):
        out |= NEEDS_QUOTE
    return out


def catalog_text(seed: int | str = 0, exclude: set[str] | frozenset = frozenset()) -> str:
    """The catalog as prompt lines, grouped, with the groups and the entries in each in a shuffled order.
    `exclude` leaves out templates this video cannot use, so the AI does not waste a scene on them."""
    rng = random.Random(str(seed))
    groups = list(GROUP_TITLES)
    rng.shuffle(groups)
    out = []
    for g in groups:
        entries = [e for e in CATALOG if e.group == g and e.name not in exclude]
        if not entries:
            continue
        rng.shuffle(entries)
        out.append(f"  {GROUP_TITLES[g]}:")
        out += [f"    {e.name}: {e.use_when}. {{\"template\": \"{e.name}\", {e.fields}}}" for e in entries]
    return "\n".join(out)


def recent_templates(outputs_root: Path, exclude: str = "", videos: int = 8) -> Counter:
    """How often each Manim template appeared in the last few OG videos (read from their storyboards)."""
    files = sorted(Path(outputs_root).glob("og-*/storyboard.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    used: Counter = Counter()
    for f in [f for f in files if f.parent.name != exclude][:videos]:
        try:
            scenes = json.loads(f.read_text(encoding="utf-8-sig")).get("scenes", [])
        except (OSError, ValueError):
            continue
        used.update({s["manim_template"]["template"] for s in scenes
                     if isinstance(s.get("manim_template"), dict) and s["manim_template"].get("template")})
    return used


_SUFFIX = r"(?:s|es|ed|d|ing|er|ers)?(?!\w)"


def _hits(e: Entry, text: str) -> int:
    """How many of the entry's keywords the text contains. Short keywords must be whole words (plus a plural or
    verb ending), so "star" does not match "start" nor "core" "scored"; long ones also match as word stems."""
    return sum(1 for k in e.keywords
               if re.search(r"(?<!\w)" + re.escape(k) + ("" if len(k) >= 6 else _SUFFIX), text))


def suggest(text: str, recent: Counter | dict | None = None, k: int = 6, seed: int | str = 0,
            exclude: set[str] | frozenset = frozenset()) -> list[str]:
    """Templates that likely fit this topic, best first: keyword matches, minus a penalty for recent use.
    The generic process/flow diagrams are left out; they are always available as a last resort."""
    text = text.lower()
    recent = recent or Counter()
    rng = random.Random(str(seed))
    scored = []
    for e in CATALOG:
        if e.name in GENERIC or e.name in exclude:
            continue
        hits = _hits(e, text)
        if hits:
            # an animation made for this kind of topic explains it best, so it ranks first and recent use
            # only nudges it; general layouts give way quickly to whatever the user has seen less
            topical = e.group in TOPICAL_GROUPS
            scored.append((hits + (2.0 if topical else 0.0) - (0.25 if topical else 0.75) * recent.get(e.name, 0)
                           + rng.random() * 0.1, e.name))
    scored.sort(reverse=True)
    return [n for _, n in scored[:k]]


TOPICAL_GROUPS = ("science", "tech")


def topical(name: str) -> bool:
    """Animations made for one kind of topic (sorting, equations, graphs, reactions, 3D science scenes)."""
    e = BY_NAME.get(name)
    return bool(e) and (e.group in TOPICAL_GROUPS or (e.group == "3d" and name not in _LAYOUT_3D))


_LAYOUT_3D = {"carousel_3d", "podium_3d", "cube_faces_3d", "spiral_timeline_3d", "bar_chart_3d"}


def fresh(recent: Counter | dict, exclude: set[str] | frozenset = frozenset(), k: int = 3, seed: int | str = 0) -> list[str]:
    """General templates the user has seen least lately, so that over a run of videos every one comes up.
    Deterministic for a given history and seed; topic animations are left to the keyword match."""
    rng = random.Random(f"fresh-{seed}")
    pool = [e.name for e in CATALOG if e.name not in GENERIC and e.name not in exclude and not topical(e.name)]
    pool.sort(key=lambda n: (recent.get(n, 0.0), rng.random()))
    return pool[:k]


# ---------------- repairs: small shape mistakes should not cost a template ----------------
# the field an AI usually means when it writes a bare string where a small object is expected
_STR_TO_OBJ = {"events": "label", "sets": "name", "branches": "name", "options": "choice", "functions": "expr",
               "series": "name", "pairs": "fact"}
_OBJ_TEXT_KEYS = ("label", "name", "title", "text", "event", "stage", "step", "item", "choice", "value")
_UNICODE_MATH = str.maketrans({"²": "^2", "³": "^3", "⁴": "^4", "−": "-", "×": "*", "÷": "/", "·": "*"})


def _as_text(v) -> str | None:
    if isinstance(v, dict):
        for k in _OBJ_TEXT_KEYS:
            if isinstance(v.get(k), (str, int, float)) and str(v[k]).strip():
                return str(v[k]).strip()
        return next((str(x) for x in v.values() if isinstance(x, str) and x.strip()), None)
    return None


def _fix_one(out: dict, err: dict) -> bool:
    loc, typ, val = err.get("loc", ()), err.get("type", ""), err.get("input")
    if not loc or not isinstance(loc[0], str) or loc[0] not in out:
        return False
    field = loc[0]
    cut = (lambda s: s[:err["ctx"]["max_length"]].rstrip()) if typ == "string_too_long" else None
    if len(loc) >= 2 and isinstance(loc[1], int) and isinstance(out[field], list) and loc[1] < len(out[field]):
        i = loc[1]
        if len(loc) >= 3 and isinstance(loc[2], str) and cut and isinstance(out[field][i], dict):
            out[field][i][loc[2]] = cut(val)
        elif typ == "string_type" and _as_text(val):
            out[field][i] = _as_text(val)
        elif typ in ("dict_type", "model_type", "model_attributes_type") and isinstance(val, str):
            out[field][i] = {_STR_TO_OBJ.get(field, "label"): val}
        elif cut and isinstance(val, str):
            out[field][i] = cut(val)
        else:
            return False
        return True
    if cut and isinstance(val, str):
        out[field] = cut(val)
        return True
    if typ == "string_type" and _as_text(val):
        out[field] = _as_text(val)
        return True
    if isinstance(out[field], list) and len(out[field]) > 2 and (typ == "too_long" or "need" in str(err.get("msg"))):
        out[field] = out[field][:-1]  # one item at a time: custom validators do not say the maximum
        return True
    return False


def repair(mt: dict) -> dict:
    """Fix the shape mistakes AI models make in otherwise good template data instead of dropping the scene:
    lists a few items too long, {"label": ..} objects where a string goes (and the reverse), text over a length
    limit, Unicode math in function_plot. It only trims or reshapes what the AI wrote and never adds text.
    Returns the input unchanged when it cannot help, so the normal validation error still explains it."""
    from pydantic import ValidationError
    if not isinstance(mt, dict) or mt.get("template") not in manim_runner.TEMPLATES:
        return mt
    out = json.loads(json.dumps(mt, ensure_ascii=False, default=str))
    for f in out.get("functions") or []:
        if isinstance(f, dict) and isinstance(f.get("expr"), str):
            f["expr"] = f["expr"].translate(_UNICODE_MATH).replace("**", "^")
    if out.get("template") == "function_plot" and isinstance(out.get("mark_x"), list):
        out["mark_x"] = out["mark_x"][:3]
    for _ in range(16):
        try:
            manim_runner.validate(out)
            return out
        except ValidationError as e:
            errs = e.errors()
        except (ValueError, TypeError):
            return mt
        # fix the first fixable error, then validate again: later errors may move once the data changes
        if not any(_fix_one(out, err) for err in errs[:1]) and not any(_fix_one(out, err) for err in errs[1:]):
            return mt
    return mt


# ---------------- variety: the same data in a different template ----------------
def _short(xs: list[str], n: int) -> bool:
    return all(0 < len(x) <= n for x in xs)


def _list_targets(head: str, items: list[str]) -> dict[str, dict]:
    """A plain list of short phrases can be shown as cards, cube faces, a mind map or a spotlight; all four only
    say "these are the parts", so none claims an order, a cause or a ranking the narration did not make."""
    items = list(dict.fromkeys(str(x).strip() for x in items if str(x).strip()))
    out = {}
    if 3 <= len(items) <= 6 and _short(items, 32):
        out["carousel_3d"] = {"template": "carousel_3d", "title": head, "items": items}
    if 2 <= len(items) <= 5 and _short(items, 32):
        out["cube_faces_3d"] = {"template": "cube_faces_3d", "title": head, "faces": items}
    if 2 <= len(items) <= 6 and _short(items, 24) and head:
        out["mind_map"] = {"template": "mind_map", "title": "", "center": head[:30],
                           "branches": [{"name": x} for x in items]}
    if 3 <= len(items) <= 8 and _short(items, 24):
        out["spotlight"] = {"template": "spotlight", "title": head, "words": items}
    return out


def alternatives(name: str, t: dict) -> dict[str, dict]:
    """Templates that can show the same data as `t` (a Manim template's params, or a Remotion visual's params
    with name "@<visual_type>"), each with the data rebuilt for it. The caller validates and grounds them."""
    head = str(t.get("title") or t.get("heading") or "")[:80]
    if name in ("process_diagram", "roadmap", "@process"):
        steps = [str(s) for s in (t.get("steps") or t.get("stops") or [])]
        out = {}
        if 2 <= len(steps) <= 6 and _short(steps, 40):
            out["roadmap"] = {"template": "roadmap", "title": head, "stops": steps}
            out["process_diagram"] = {"template": "process_diagram", "title": head, "steps": steps}
        # cards and cube faces also show their items one after another, so the order survives
        out.update({k: v for k, v in _list_targets(head, steps).items() if k in ("carousel_3d", "cube_faces_3d")})
        return out
    if name in ("carousel_3d", "cube_faces_3d", "spotlight", "@key_points"):
        items = t.get("items") or t.get("faces") or t.get("words") or t.get("points") or []
        return _list_targets(head, [str(x) for x in items])
    if name == "mind_map" and not any(isinstance(b, dict) and b.get("items") for b in t.get("branches") or []):
        names = [b.get("name", "") if isinstance(b, dict) else str(b) for b in t.get("branches") or []]
        return _list_targets(str(t.get("center") or head), names)
    if name in ("timeline", "spiral_timeline_3d", "@timeline"):
        events = t.get("events") or []
        labels = [e.get("label", "") if isinstance(e, dict) else str(e) for e in events]
        out = {}
        if 2 <= len(labels) <= 6 and all(labels):
            out["timeline"] = {"template": "timeline", "title": head,
                               "events": [e if isinstance(e, dict) else {"label": str(e)} for e in events]}
            if _short(labels, 24):
                out["spiral_timeline_3d"] = {"template": "spiral_timeline_3d", "title": head, "events": labels}
        return out
    if name in ("simple_chart", "bar_chart_3d", "@chart"):
        labels, values = [str(x) for x in t.get("labels") or []], list(t.get("values") or [])
        if not (2 <= len(labels) == len(values) <= 8):
            return {}
        unit = str(t.get("unit", ""))[:12]
        out = {k: {"template": k, "title": head, "labels": labels, "values": values, "unit": unit}
               for k in ("simple_chart", "bar_chart_3d")}
        if len(labels) <= 6 and _short(labels, 28):
            order = sorted(range(len(labels)), key=lambda i: -float(values[i]))
            out["ranking"] = {"template": "ranking", "title": head, "items": [labels[i] for i in order],
                              "values": [values[i] for i in order], "unit": unit}
        return out
    if name == "@comparison":
        lp, rp = list(t.get("leftPoints") or []), list(t.get("rightPoints") or [])
        if (lp or rp) and len(lp) <= 4 and len(rp) <= 4:
            return {"before_after": {"template": "before_after", "title": head, "mode": "versus",
                                     "left_title": str(t.get("leftTitle", ""))[:24],
                                     "right_title": str(t.get("rightTitle", ""))[:24],
                                     "left_points": lp, "right_points": rp}}
        return {}
    if name == "@stat" and t.get("value") is not None:
        pct = t.get("suffix") == "%" and 0 <= float(t["value"]) <= 100
        return {"stat_reveal": {"template": "stat_reveal", "title": "", "value": t["value"],
                                "prefix": str(t.get("prefix", ""))[:6], "suffix": str(t.get("suffix", ""))[:12],
                                "label": str(t.get("label", ""))[:60], "style": "ring" if pct else "counter"}}
    return {}


def narration_list(lines: list[str], head: str) -> dict[str, dict]:
    """Last resort for a plain text scene: its narration as a list, when the narration is made of short whole
    phrases (2-5 words each, never cut mid-sentence), so every word on screen is a word the voice says."""
    parts = [p for line in lines for p in re.split(r"(?<=[.!?;:])\s+|,\s+(?:and |but |so |or )?", line)]
    items = [re.sub(r"[.!?;:,]+$", "", p.strip()) for p in parts if p.strip()]
    if not items or any(not 2 <= len(x.split()) <= 5 for x in items):
        return {}
    return _list_targets(head, items[:5]) if len(items) >= 2 else {}


def recent_weights(outputs_root: Path, exclude: str = "", videos: int = 12) -> dict[str, float]:
    """Recency-weighted use of each template in the last `videos` OG videos: the newest video counts 1.0 and
    each older one 0.8 times the one after it, so last video's picks weigh far more than last week's."""
    files = sorted(Path(outputs_root).glob("og-*/storyboard.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    w: dict[str, float] = {}
    for age, f in enumerate([f for f in files if f.parent.name != exclude][:videos]):
        try:
            scenes = json.loads(f.read_text(encoding="utf-8-sig")).get("scenes", [])
        except (OSError, ValueError):
            continue
        for t in {s["manim_template"]["template"] for s in scenes
                  if isinstance(s.get("manim_template"), dict) and s["manim_template"].get("template")}:
            w[t] = w.get(t, 0.0) + 0.8 ** age
    return w


# ---------------- builders: a template filled from the scene itself ----------------
# Used when the AI named a template but left its data out, and by the variety pass to turn text scenes into
# animations. Text comes only from the narration (short phrases of its own words) or from neutral labels
# ("Input", "Plan"); numbers only appear as a clearly labelled example (sorting bars, a sample graph).
_STOP = set("a an the and or but so then this that these those it its is are was were be been we you they our "
            "your their to of in on at by for with from as into about which who what when how why just also very "
            "can will would could should may might do does did not no all each every more most here there now "
            "first next finally let lets exact same specific new both really whole almost own back along between up down "
            "out off over use uses".split())
# templates whose fields claim a structure (a loop, layers, a cause chain) or show a topic's own animation: built
# only when the topic's keywords match; the rest only say "these are the parts" and fit any scene
NEUTRAL = {"process_diagram", "roadmap", "carousel_3d", "cube_faces_3d", "spotlight", "mind_map"}
_ALGOS = (("merge sort", None), ("heap sort", None), ("radix sort", None), ("counting sort", None),
          ("quick sort", "quick_sort"), ("quicksort", "quick_sort"), ("bubble", "bubble_sort"),
          ("selection sort", "selection_sort"), ("insertion", "insertion_sort"), ("binary search", "binary_search"),
          ("linear search", "linear_search"), ("sort", "quick_sort"), ("search", "binary_search"))
EXAMPLE_VALUES = [6, 3, 8, 2, 9, 4, 7]
_FUNCS = (("parabola", "x^2 - 4"), ("quadratic", "x^2 - 4"), ("sine", "sin(x)"), ("trigonometr", "sin(x)"),
          ("cosine", "cos(x)"), ("exponential", "exp(x/2)"), ("logarithm", "log(x)"), ("derivative", "x^3 - 3*x"),
          ("calculus", "x^3 - 3*x"), ("cubic", "x^3 - 3*x"), ("linear", "2*x + 1"), ("slope", "2*x + 1"))
_MOLECULES = ("water", "carbon dioxide", "methane", "ammonia", "ethylene", "benzene", "oxygen", "ethanol")
_SOLIDS = ("cube", "tetrahedron", "octahedron", "dodecahedron", "icosahedron", "sphere", "cylinder", "cone", "torus")
_PLANETS = ("Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune")
_EQUATION = re.compile(r"(?<![A-Za-z])(?:\d|\(|[A-Za-z](?![A-Za-z]))[\w ^()+\-*/²³.]*?=[\w ^()+\-*/²³.]*[\w)]")


def _cut(s: str, n: int) -> str:
    """At most n characters, cut at a word boundary."""
    return s if len(s) <= n else (s[:n + 1].rsplit(" ", 1)[0] if " " in s[:n + 1] else s[:n])


def phrases(lines: list[str], n: int = 5) -> list[str]:
    """Short labels made of the narration's own words: one per sentence or clause, leading and trailing filler
    words dropped, at most `n` words, never a number (numbers belong to the fact checks)."""
    out = []
    for line in lines:
        for part in re.split(r"(?<=[.!?;:])\s+|,\s+|\s+(?:and|then|so|but|because|which|while|until)\s+", line):
            words = re.findall(r"[A-Za-z][A-Za-z'\-]*", part)
            while words and words[0].lower() in _STOP:
                words.pop(0)
            words = words[:n]
            while words and words[-1].lower() in _STOP:
                words.pop()
            if len(words) >= 2 or (words and len(words[0]) > 4):
                p = " ".join(words)
                out.append(p[0].upper() + p[1:])
    return list(dict.fromkeys(out))


def fits(text: str, min_hits: int = 1) -> set[str]:
    """Templates with at least `min_hits` of their topic keywords in the text."""
    text = text.lower()
    return {e.name for e in CATALOG if _hits(e, text) >= min_hits}


def _first(text: str, table) -> str | None:
    return next((v for k, v in table if k in text), None)


def build(name: str, head: str, items: list[str], topic: str, lines: list[str] = ()) -> dict | None:
    """`name` filled from a scene: its heading, short phrases of its narration (`items`), its narration `lines`
    and the video's topic text (for example values that match it). None when the scene cannot fill it honestly:
    templates whose fields claim something specific (a ranking, pros and cons, a quote, numbers) are never
    guessed, and topic animations (sorting, graphs, molecules) only get neutral example data."""
    head, topic = _cut(str(head or ""), 60), topic.lower()
    if name not in NEUTRAL and name not in fits(topic):
        return None
    items = [_cut(x, 32) for x in items if x][:6]
    t: dict = {"template": name, "title": head}
    if name in ("process_diagram", "roadmap") and len(items) >= 2:
        t["steps" if name == "process_diagram" else "stops"] = items[:6]
    elif name == "cycle_diagram" and len(items) >= 3:
        t.update(stages=items[:6], center=_cut(head, 30))
    elif name == "domino_chain" and len(items) >= 3:
        t.update(links=items[:5][:-1], effect=items[:5][-1])
    elif name == "pyramid" and len(items) >= 2:
        t["levels"] = items[:6]
    elif name in ("carousel_3d", "cube_faces_3d", "spotlight", "mind_map"):
        if name in ("spotlight", "mind_map") and lines:
            items = phrases(lines, 3)[:6]  # their labels are short
        return _list_targets(head or (items[0] if items else ""), items).get(name)
    elif name in ("layer_stack_3d", "planet_layers_3d") and len(items) >= 2:
        t["layers"] = [_cut(x, 24) for x in items[:5]]
    elif name == "spiral_timeline_3d" and len(items) >= 2:
        t["events"] = [_cut(x, 24) for x in items[:6]]
    elif name == "array_algorithm":
        algo = next((v for k, v in _ALGOS if k in topic), None)
        if not algo:  # no sort or search it can run: an example of a different one would mislead
            return None
        vals = sorted(EXAMPLE_VALUES) if algo == "binary_search" else EXAMPLE_VALUES
        t.update(title=f"Example: {algo.replace('_', ' ')}", algorithm=algo, values=vals)
        if algo.endswith("_search"):
            t["target"] = vals[4]
    elif name == "node_graph":
        if not any(k in topic for k in ("graph", "bfs", "dfs", "dijkstra", "breadth", "depth first", "shortest path",
                                        "node")):
            return None
        t.update(title=head or "Example graph", nodes=list("ABCDEF"),
                 edges=[["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"], ["C", "E"], ["D", "F"], ["E", "F"]],
                 path=list("ABCDEF") if ("bfs" in topic or "breadth" in topic) else ["A", "C", "E", "F"],
                 directed="direct" in topic)
    elif name == "function_plot":
        expr = _first(topic, _FUNCS)
        if not expr:
            return None
        t.update(functions=[{"expr": expr, "label": ""}], x_min=0.1 if "log" in expr else -5, x_max=5)
    elif name == "equation_steps":
        eqs = [re.sub(r"\s+", " ", m).strip() for line in lines for m in _EQUATION.findall(line)]
        eqs = [e for e in dict.fromkeys(eqs) if len(e) <= 48]
        if len(eqs) < 2:
            return None
        t["lines"] = eqs[:6]
    elif name == "agent_loop":
        t.update(goal=head, steps=["Plan", "Act", "Observe"])
    elif name == "security_flow":
        attack = next((a for k, a in (("phishing", "Phishing email"), ("malware", "Malware"), ("password", "Password guess"),
                                      ("intercept", "Interception"), ("encrypt", "Interception"), ("https", "Interception"))
                       if k in topic), "Attack")
        defense = next((d for k, d in (("encrypt", "Encryption"), ("https", "Encryption"), ("filter", "Spam filter"),
                                       ("firewall", "Firewall")) if k in topic), "Defence")
        t.update(attack=attack, defense=defense, target="You", outcome="blocked", encrypted=defense == "Encryption")
    elif name == "neural_net_3d":
        t["layers"] = ["Input", "Hidden", "Output"]
    elif name == "orbit_3d":
        planets = [p for p in _PLANETS if p.lower() in topic]
        if planets or "planet" in topic or "solar" in topic:
            t.update(kind="planets", center="Sun", orbiters=planets[:6] or ["Planet"])
        elif not any(k in topic for k in ("atom", "electron", "nucleus")):
            return None
        else:
            t.update(kind="atom", center="Nucleus", orbiters=["Electron", "Electron"])
    elif name == "surface_3d":
        t["surface"] = "saddle" if "saddle" in topic else "waves" if "wave" in topic else "paraboloid"
    elif name == "vector_field_3d":
        t["field"] = "dipole" if "magnet" in topic else "vortex" if ("vortex" in topic or "curl" in topic) else \
            "uniform" if "uniform" in topic else "source"
    elif name == "wave_3d":
        t["kind"] = "electromagnetic" if any(k in topic for k in ("light", "electromagnetic", "radio")) \
            else "longitudinal" if "sound" in topic else "transverse"
    elif name == "crystal_lattice_3d":
        t["lattice"] = "salt" if "salt" in topic else "body_centered" if "iron" in topic else \
            "face_centered" if ("metal" in topic or "copper" in topic) else "simple_cubic"
    elif name == "molecule_3d":
        mol = next((m for m in _MOLECULES if m in topic), None)
        if not mol:
            return None
        t["molecule"] = mol.replace(" ", "_")
    elif name == "solids_3d":
        t["shapes"] = [s for s in _SOLIDS if s in topic][:4] or ["cube", "sphere"]
    elif name in ("dna_helix_3d", "galaxy_3d"):
        pass
    elif name == "globe_3d" and len(items) >= 2:
        t["hubs"] = [_cut(x, 20) for x in items[:6]]
    else:
        return None
    try:
        manim_runner.validate(t)
    except (ValueError, TypeError):
        return None
    return t
