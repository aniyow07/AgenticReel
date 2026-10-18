"""Agent 3: Scriptwriter -> script.md + script.json"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from agents.base import AgentContext, ask_llm, brief_summary, words_budget
from retrieval.index import STOP
from schemas.artifacts import Facts, Plan, Script, ScriptSegment

PROMPT_VERSION = "scriptwriter/v3"

SYSTEM_OG = """You are the Scriptwriter agent for a polished motion-graphics explainer.
Write narration with a strong opening, a clear explanation, structure, and a useful close or CTA."""
SYSTEM_BRAINROT = """You are the Scriptwriter agent for a fast, narration-driven short over gameplay footage.
Open with a hook, keep sentences short and conversational, allow humor and suspense, and do not force slang."""
RULES = """Rules:
- Total narration must be close to {words} words (it must fit {seconds:.0f} seconds at a natural pace).
- Split narration into segments of 6-22 words, one or two short sentences each.
- Factual content: every factual statement must come from the SUPPORTED FACTS list and cite its fact_ids.
  Never add numbers, statistics, names or claims that are not in that list. If facts are thin, stay general.
- Worked math is not a factual claim: when explaining math, walk through the steps and write each equation
  with digits and "=" (for example "2x + 3 = 11, so 2x = 8") so it can be animated on screen.
- Fiction: invented events are fine, but do not present them as real facts.
- Keep every fact in its own context: never merge separate facts into one claim or attribute an achievement,
  skill or certification to the wrong job, project or source. Do not add skills, tools or results that are
  not in the facts.
- If a CTA is given, end with it as the final segment.
- Respect must_include and must_avoid.
- highlights: 1-2 important words from that segment's own text.
Return ONLY JSON: {{"title": "...", "segments": [{{"text": "...", "beat": "...", "fact_ids": [], "highlights": []}}], "cta": "..."}}"""


# an equation being worked: "2x + 3 = 11", "x equals 4"
MATH_WORK = re.compile(r"[\w)²³]\s*=\s*[-\w(√]|\b[a-z]\s+(equals|is equal to)\b", re.I)


class SegLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    text: str = Field(min_length=2, max_length=400)
    beat: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class ScriptLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    title: str = Field(min_length=2, max_length=120)
    segments: list[SegLLM] = Field(min_length=2, max_length=40)
    cta: str = ""


def split_long(text: str, max_words: int = 22) -> list[str]:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    out = []
    for s in sents:
        w = s.split()
        while len(w) > max_words:
            cut = max_words
            for i in range(max_words - 1, max_words // 2, -1):
                if w[i].endswith((",", ";", ":")):
                    cut = i + 1
                    break
            out.append(" ".join(w[:cut]))
            w = w[cut:]
        if w:
            out.append(" ".join(w))
    return out


def pick_highlights(text: str, n: int = 2) -> list[str]:
    words = [re.sub(r"[^\w'-]", "", w) for w in text.split()]
    cands = [w for w in words if w and w.lower() not in STOP and len(w) > 3]
    cands.sort(key=lambda w: (-(w[0].isupper() or any(ch.isdigit() for ch in w)), -len(w)))
    return cands[:n]


def clean_topic(topic: str, audience: str = "") -> str:
    """Turn an instruction-shaped brief ("Explain X to Y") into the subject ("X") for local templates."""
    t = topic.strip().rstrip(".!")
    t = re.sub(r"^(please\s+)?(make|create|write|produce|generate)\s+(a|an)?\s*(short\s+)?(video|explainer|reel|story)"
               r"(\s+(about|on|explaining))?\s+", "", t, flags=re.I)
    t = re.sub(r"^(explain|describe|tell|narrate|introduce|teach)\s+(me\s+|us\s+)?(about\s+)?", "", t, flags=re.I)
    t = re.sub(r"\s+(to|for)\s+(school\s+|college\s+|high\s+school\s+)?(students|kids|children|beginners|adults|"
               r"teens|everyone|an?\s+\w+\s+audience)\b.*$", "", t, flags=re.I)
    return t.strip() or topic.strip()


def _sentence(s: str) -> str:
    s = s.strip()
    return s if s.endswith((".", "!", "?")) else s + "."


def local_script(ctx: AgentContext, plan: Plan, facts: Facts) -> ScriptLLM:
    b = ctx.brief
    budget = words_budget(b.duration_s, b.mode, ctx.speed_pct)
    topic = clean_topic(b.topic, b.audience).rstrip(".?! ")
    if len(topic) > 1 and topic[1:2].islower() and not b.topic.strip().endswith("?"):
        topic = topic[0].lower() + topic[1:]  # "How rainbows form" -> "how rainbows form" mid-sentence
    segs: list[tuple[str, str, list[str]]] = []
    brainrot = b.mode != "og"
    if b.content_type == "fictional_story":
        segs = [
            (f"Okay, this one starts normal: {topic}." if brainrot else f"Imagine this: {topic}.", "hook", []),
            ("At first, everything seemed completely ordinary.", "setup", []),
            ("Then one small detail did not add up, and nobody could explain it.", "rising tension", []),
            ("The closer they looked, the stranger it got.", "rising tension", []),
            ("And when the truth finally came out, it was not what anyone expected.", "twist", []),
            ("Some stories end quietly. This one did not.", "resolution", []),
        ]
    else:
        hook = (f"Here is something worth knowing about {topic}." if not topic.endswith("?") and "?" not in b.topic
                else f"{b.topic.strip()}")
        if brainrot:
            hook = (f"Okay, real question: {b.topic.strip()}" if b.topic.strip().endswith("?")
                    else f"Wait, let's talk about {topic}.")
        segs.append((_sentence(hook), "hook", []))
        supported = facts.supported()
        if supported:
            segs.append((f"Here is what the sources say.", "core idea", []))
            for f in supported:
                for part in split_long(_sentence(f.claim)):
                    segs.append((part, "key points", [f.fact_id]))
        else:
            segs.append((f"This is a quick overview for {b.audience.lower()}.", "core idea", []))
            for item in b.must_include:
                segs.append((_sentence(item), "key points", []))
            segs.append(("We will keep it general and skip specific numbers we could not check.", "key points", []))
        segs.append((f"So next time {topic.lower()} comes up, you will know where to start." if not b.cta
                     else _sentence(b.cta), "takeaway", []))
    # Fit the word budget: drop middle segments from the end until it fits.
    def wc(items):
        return sum(len(t.split()) for t, _, _ in items)
    while wc(segs) > budget * 1.1 and len(segs) > 3:
        segs.pop(-2)
    title = topic[:1].upper() + topic[1:]
    return ScriptLLM(title=title[:120], cta=b.cta,
                     segments=[SegLLM(text=t, beat=beat, fact_ids=ids, highlights=pick_highlights(t))
                               for t, beat, ids in segs])


def check_script(script: Script, facts: Facts, ctx: AgentContext) -> list[str]:
    """Deterministic checks shared by the scriptwriter and the critic."""
    issues = []
    b = ctx.brief
    budget = words_budget(b.duration_s, b.mode, ctx.speed_pct)
    wc = script.word_count
    if wc > budget * 1.25:
        issues.append(f"script has {wc} words, budget is about {budget}")
    if wc < budget * 0.5 and not b.dev_short:
        issues.append(f"script has only {wc} words; target about {budget}")
    known = {f.fact_id: f for f in facts.facts}
    # numbers the person wrote in the brief are theirs to use (e.g. the equation they asked about)
    supported_text = " ".join([f.evidence + " " + f.claim for f in facts.supported()] + [b.topic, *b.must_include])
    for s in script.segments:
        for fid in s.fact_ids:
            if fid not in known:
                issues.append(f"{s.segment_id} cites unknown fact {fid}")
            elif known[fid].status == "unsupported":
                issues.append(f"{s.segment_id} cites unsupported fact {fid}")
        # Worked math ("2x + 3 = 11, so 2x = 8") is calculation, not a factual claim needing a source.
        if b.content_type != "fictional_story" and not MATH_WORK.search(s.text):
            for n in re.findall(r"\d+(?:[.,]\d+)?", s.text):
                if n.replace(",", "") not in supported_text.replace(",", ""):
                    issues.append(f"{s.segment_id} states the number {n} which no supported fact contains")
    low = " ".join(s.text.lower() for s in script.segments)
    for avoid in b.must_avoid:
        if avoid.lower() in low:
            issues.append(f"script mentions something the brief asked to avoid: {avoid!r}")
    return issues


def to_script(data: ScriptLLM, origin: str) -> Script:
    segs = []
    for s in data.segments:
        for part in split_long(s.text):
            hl = [h for h in s.highlights if h.lower() in part.lower()][:2] or pick_highlights(part, 1)
            segs.append(ScriptSegment(segment_id=f"N{len(segs) + 1:02d}", text=part, beat=s.beat,
                                      fact_ids=s.fact_ids, highlights=hl))
    return Script(title=data.title, segments=segs, cta=data.cta, origin=origin)  # type: ignore[arg-type]


def remove_unsupported(script: Script, issues: list[str]) -> Script:
    """Repair: drop segments that carry unsupported numbers or facts (keeps at least two)."""
    bad = {m.group(1) for i in issues for m in [re.match(r"(N\d+) ", i)] if m}
    keep = [s for s in script.segments if s.segment_id not in bad]
    if len(keep) >= 2:
        script = script.model_copy(update={"segments": keep, "origin": "repair"})
    return script


def run(ctx: AgentContext, plan: Plan, facts: Facts, feedback: list[str] | None = None) -> Script:
    b = ctx.brief
    words = words_budget(b.duration_s, b.mode, ctx.speed_pct)
    fact_lines = "\n".join(f"- {f.fact_id} [{f.status}]: {f.claim}" for f in facts.facts) or "(none)"
    user = (f"Brief:\n{brief_summary(b)}\n\nPlan beats: {plan.narrative_structure}\n\nSUPPORTED FACTS (only "
            f"'supported' and 'user_provided' may be stated):\n{fact_lines}\n\nResearch limitations: "
            f"{facts.limitations}\n")
    if feedback:
        user += "\nFix these problems from the previous draft:\n- " + "\n- ".join(feedback)
    system = (SYSTEM_OG if b.mode == "og" else SYSTEM_BRAINROT) + "\n" + RULES.format(words=words,
                                                                                         seconds=b.duration_s)
    data = ask_llm(ctx, "scripting", system, user, ScriptLLM, PROMPT_VERSION, temperature=0.8, max_tokens=2500)
    script = to_script(data, "llm") if data else to_script(local_script(ctx, plan, facts), "local")
    issues = check_script(script, facts, ctx)
    if issues and data:
        ctx.job.log.log("scripting", "validator", "issues", issues=issues)
        retry = ask_llm(ctx, "scripting", system, user + "\nYour draft had problems:\n- " + "\n- ".join(issues),
                        ScriptLLM, PROMPT_VERSION, temperature=0.5, max_tokens=2500)
        if retry:
            script = to_script(retry, "llm")
            issues = check_script(script, facts, ctx)
    if any("states the number" in i or "unsupported fact" in i or "unknown fact" in i for i in issues):
        script = remove_unsupported(script, issues)
    if script.word_count > words * 1.25:  # trim from the end, keeping the closing line
        segs = script.segments
        while sum(len(s.text.split()) for s in segs) > words * 1.1 and len(segs) > 3:
            segs = segs[:-2] + segs[-1:]
        script = script.model_copy(update={"segments": segs})
    return script


