"""Agent 1: Planner -> plan.json"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agents.base import AgentContext, ask_llm, brief_summary, words_budget
from schemas.artifacts import Plan

PROMPT_VERSION = "planner/v3"

SYSTEM = """You are the Planner agent of AgentReel, a short-form video generator.
Plan ONE video for the brief. Adapt to the brief: do not reuse a generic template.
Rules:
- OG mode: motion-graphics explainer; you may reserve 0-2 beats for Manim diagrams
  (process, flow, timeline, chart from supplied numbers only, step-by-step equations for math,
  chemical reactions for chemistry, sorting/searching for algorithms, an agent loop for agentic AI, an
  attack-and-defence flow for cybersecurity, function graphs, line and pie charts from supplied numbers, network graphs). Topics like these should use them.
- minecraft/subway modes: narration-driven over gameplay; keep the structure simple and fast.
- research_required is true for factual, promotional or awareness content.
- Return ONLY a JSON object with the requested keys."""


class PlanLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    goal: str
    narrative_structure: list[str] = Field(min_length=2, max_length=10)
    scene_count: int = Field(ge=1, le=14)
    research_required: bool
    research_questions: list[str] = Field(default_factory=list, max_length=8)
    visual_strategy: str
    manim_scenes: list[str] = Field(default_factory=list, max_length=3)
    needed_assets: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(min_length=1, max_length=8)


def local_plan(ctx: AgentContext) -> PlanLLM:
    b = ctx.brief
    brainrot = b.mode != "og"
    if b.content_type == "fictional_story":
        structure = ["hook", "setup", "rising tension", "twist", "resolution"]
    elif b.content_type == "promotional":
        structure = ["hook", "what it is", "key benefits", "proof from supplied facts", "call to action"]
    elif b.content_type == "awareness":
        structure = ["hook", "why it matters", "key facts", "what you can do", "closing"]
    else:
        structure = ["hook", "core idea", "how it works", "key points", "takeaway"]
    if b.cta and "call to action" not in structure:
        structure.append("call to action")
    scenes = max(3, min(10, round(b.duration_s / (5 if brainrot else 6))))
    manim = [] if brainrot or b.content_type == "fictional_story" else ["how it works"]
    return PlanLLM(
        goal=f"{'Tell' if b.content_type == 'fictional_story' else 'Explain'} '{b.topic}' to {b.audience} "
             f"in a {b.tone} tone.",
        narrative_structure=structure, scene_count=scenes,
        research_required=b.is_factual,
        research_questions=[b.topic, *b.must_include][:6],
        visual_strategy=("Real gameplay background with large synced captions and keyword highlights"
                         if brainrot else "Animated titles, key-point cards, diagrams and an end card"),
        manim_scenes=manim, needed_assets=["narration audio"] + (["gameplay footage"] if brainrot else []),
        success_criteria=["Addresses the brief's topic and audience", f"Runs about {b.duration_s:.0f}s",
                          "Captions match narration", "No unsupported factual claims"],
    )


def run(ctx: AgentContext) -> Plan:
    b = ctx.brief
    user = (f"Brief:\n{brief_summary(b)}\n\nReturn JSON with keys: goal, narrative_structure (list of beats), "
            f"scene_count, research_required, research_questions, visual_strategy, manim_scenes (beats suited to "
            f"a Manim diagram, OG only), needed_assets, success_criteria.")
    data = ask_llm(ctx, "planning", SYSTEM, user, PlanLLM, PROMPT_VERSION, temperature=0.4, max_tokens=1500)
    origin = "llm" if data else "local"
    data = data or local_plan(ctx)
    if b.mode != "og":
        data.manim_scenes = []
    words = words_budget(b.duration_s, b.mode)
    return Plan(goal=data.goal, audience=b.audience, tone=b.tone, content_type=b.content_type, mode=b.mode,
                narrative_structure=data.narrative_structure, target_duration_s=b.duration_s,
                scene_count=max(2, min(data.scene_count, 12)),
                research_required=data.research_required or b.is_factual,
                research_questions=data.research_questions, visual_strategy=data.visual_strategy,
                manim_scenes=data.manim_scenes[:2], needed_assets=data.needed_assets,
                estimated_narration_words=words,
                estimated_api_calls=0 if ctx.mode == "LOCAL_ONLY" else 5,
                success_criteria=data.success_criteria, origin=origin)
