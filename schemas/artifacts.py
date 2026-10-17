"""Validated artifacts produced by each agent stage."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.render_props import PARAM_MODELS, VISUAL_TYPES_BRAINROT, VISUAL_TYPES_OG

Origin = Literal["llm", "local", "repair", "user"]


# ---------------- Planner ----------------
class Plan(BaseModel):
    goal: str = Field(min_length=3)
    audience: str
    tone: str
    content_type: str
    mode: Literal["og", "minecraft", "subway"]
    narrative_structure: list[str] = Field(min_length=2, max_length=10)
    target_duration_s: float = Field(gt=0)
    scene_count: int = Field(ge=1, le=14)
    research_required: bool
    research_questions: list[str] = Field(default_factory=list, max_length=10)
    visual_strategy: str
    manim_scenes: list[str] = Field(default_factory=list, description="beats that suit a Manim template")
    needed_assets: list[str] = Field(default_factory=list)
    estimated_narration_words: int = Field(ge=5)
    estimated_api_calls: int = Field(ge=0)
    success_criteria: list[str] = Field(min_length=1)
    origin: Origin = "local"


# ---------------- Researcher ----------------
class Fact(BaseModel):
    fact_id: str
    claim: str = Field(min_length=3)
    source_id: str | None = None
    source: str | None = None
    page: int | None = None
    heading: str | None = None
    evidence: str = ""
    status: Literal["supported", "user_provided", "unsupported", "assumption"]

    @model_validator(mode="after")
    def _evidence(self):
        if self.status == "supported" and (not self.source_id or not self.evidence.strip()):
            raise ValueError(f"{self.fact_id}: a supported fact needs a source_id and evidence")
        return self


class Source(BaseModel):
    source_id: str
    name: str
    kind: str
    pages: int | None = None
    chars: int = 0


class Facts(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_performed: bool = True
    origin: Origin = "local"

    def supported(self) -> list[Fact]:
        return [f for f in self.facts if f.status in ("supported", "user_provided")]


# ---------------- Scriptwriter ----------------
class ScriptSegment(BaseModel):
    segment_id: str
    text: str = Field(min_length=2, max_length=400)
    beat: str = ""
    fact_ids: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list, max_length=4)


class Script(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    segments: list[ScriptSegment] = Field(min_length=1, max_length=40)
    cta: str = ""
    words_per_minute: float = 155
    origin: Origin = "local"

    @field_validator("segments")
    @classmethod
    def _unique(cls, v):
        ids = [s.segment_id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("segment ids must be unique")
        return v

    @property
    def word_count(self) -> int:
        return sum(len(s.text.split()) for s in self.segments)

    def estimated_seconds(self) -> float:
        return self.word_count / self.words_per_minute * 60

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        for s in self.segments:
            refs = f"  _(facts: {', '.join(s.fact_ids)})_" if s.fact_ids else ""
            lines.append(f"**{s.segment_id}** [{s.beat}] {s.text}{refs}")
            lines.append("")
        if self.cta:
            lines += [f"**CTA:** {self.cta}", ""]
        lines.append(f"_Words: {self.word_count}, estimated {self.estimated_seconds():.1f}s at "
                     f"{self.words_per_minute:.0f} wpm_")
        return "\n".join(lines)


# ---------------- Storyboarder ----------------
class StoryboardScene(BaseModel):
    scene_id: str
    start_time: float = Field(ge=0)
    duration: float = Field(gt=0)
    narration_segment_ids: list[str] = Field(min_length=1)
    on_screen_text: str = ""
    visual_type: str
    visual_parameters: dict = Field(default_factory=dict)
    asset_references: list[str] = Field(default_factory=list)
    transition: Literal["fade", "slide", "zoom", "none"] = "fade"
    backdrop: str = ""  # OG background style chosen by the storyboard ("" = Editor picks)
    source_references: list[str] = Field(default_factory=list)
    manim_template: dict | None = Field(default=None, description="validated params for a trusted Manim template")


class Storyboard(BaseModel):
    mode: Literal["og", "minecraft", "subway"]
    scenes: list[StoryboardScene] = Field(min_length=1)
    origin: Origin = "local"

    @model_validator(mode="after")
    def _check(self):
        allowed = VISUAL_TYPES_OG if self.mode == "og" else VISUAL_TYPES_BRAINROT
        for s in self.scenes:
            if s.visual_type not in allowed:
                raise ValueError(f"scene {s.scene_id}: visual type {s.visual_type!r} is not allowed in "
                                 f"{self.mode} mode")
            if s.visual_type in PARAM_MODELS and s.visual_type not in ("image", "manim"):
                PARAM_MODELS[s.visual_type].model_validate(s.visual_parameters)
        ids = [s.scene_id for s in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene ids must be unique")
        return self

    def validate_against(self, script: Script, target_s: float, tol: float = 0.15) -> list[str]:
        """Problems that need a repair; empty list means OK."""
        issues = []
        seg_ids = [s.segment_id for s in script.segments]
        used = [i for s in self.scenes for i in s.narration_segment_ids]
        missing = [i for i in seg_ids if i not in used]
        unknown = [i for i in used if i not in seg_ids]
        if missing:
            issues.append(f"segments not placed in any scene: {missing}")
        if unknown:
            issues.append(f"scenes reference unknown segments: {unknown}")
        if len(used) != len(set(used)):
            issues.append("a narration segment is used by more than one scene")
        if used and [i for i in seg_ids if i in used] != used:
            issues.append("scenes do not follow the script order")
        t = 0.0
        for s in sorted(self.scenes, key=lambda x: x.start_time):
            if abs(s.start_time - t) > 0.05:
                issues.append(f"scene {s.scene_id} starts at {s.start_time:.2f}s, expected {t:.2f}s (gap/overlap)")
            t = s.start_time + s.duration
        if target_s and abs(t - target_s) > target_s * tol:
            issues.append(f"storyboard covers {t:.1f}s but the target is {target_s:.1f}s")
        return issues


# ---------------- Assets ----------------
class AssetEntry(BaseModel):
    asset_id: str
    kind: Literal["narration", "narration_segment", "gameplay", "background_video", "music", "image", "manim_clip"]
    path: str
    exists: bool
    sha256: str | None = None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    source: str = ""
    license: str = ""
    review_status: str = ""
    notes: str = ""


class SegmentAudio(BaseModel):
    segment_id: str
    path: str
    duration_s: float = Field(gt=0)
    word_timings: list[tuple[str, float, float]] = Field(default_factory=list)  # (word, start_s, end_s)
    provider: str


class AssetManifest(BaseModel):
    assets: list[AssetEntry] = Field(default_factory=list)
    segments: list[SegmentAudio] = Field(default_factory=list)
    narration_path: str | None = None
    narration_provider: str | None = None
    gameplay_clip_ids: list[str] = Field(default_factory=list)
    background_path: str | None = None
    music_path: str | None = None
    manim_clips: dict[str, str] = Field(default_factory=dict)  # scene_id -> clip path
    missing: list[str] = Field(default_factory=list)


# ---------------- QA ----------------
class QACheck(BaseModel):
    name: str
    passed: bool
    severity: Literal["error", "warning", "info"] = "error"
    detail: str = ""
    route_to: str | None = None


class QAReport(BaseModel):
    technical_pass: bool
    semantic_status: Literal["approved", "needs_changes", "not_reviewed"]
    checks: list[QACheck]
    semantic_notes: list[str] = Field(default_factory=list)
    repairs_attempted: int = 0
    is_test_render: bool = False
    output: dict = Field(default_factory=dict)

    @property
    def failures(self) -> list[QACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]
