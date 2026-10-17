"""Shared agent plumbing: context object and the LLM-or-local decision."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from core.config import Settings
from core.jobs import Job
from providers.openrouter import AuthError, BudgetExceeded, LLMError, OpenRouterClient, QuotaExhausted
from schemas.brief import Brief

T = TypeVar("T", bound=BaseModel)


class AgentFailure(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


@dataclass
class AgentContext:
    job: Job
    brief: Brief
    settings: Settings
    llm: OpenRouterClient | None
    seed: int = 42
    notes: list[str] = field(default_factory=list)

    @property
    def mode(self) -> str:
        return self.settings.execution_mode

    @property
    def rng(self) -> random.Random:
        return random.Random(self.seed)

    rate_override: str | None = None

    @property
    def tts_rate(self) -> str:
        return self.rate_override or self.settings.tts_rate

    @property
    def voice(self) -> str:
        return self.brief.voice or self.settings.tts_voice

    def llm_enabled(self) -> bool:
        return self.mode != "LOCAL_ONLY" and self.llm is not None


def brief_summary(b: Brief) -> str:
    return json.dumps({k: v for k, v in b.model_dump().items()
                       if k not in ("source_text", "source_files", "narration_audio", "music")}, ensure_ascii=False)


def ask_llm(ctx: AgentContext, stage: str, system: str, user: str, schema: type[T], prompt_version: str,
            **kw) -> T | None:
    """Call the LLM according to the execution mode.

    Returns the validated object, or None when the caller should use its local fallback
    (AI_PREFERRED only). AI_REQUIRED raises AgentFailure instead of falling back.
    """
    if ctx.mode == "LOCAL_ONLY":
        return None
    if ctx.llm is None:
        if ctx.mode == "AI_REQUIRED":
            raise AgentFailure(stage, "AI_REQUIRED mode but no OpenRouter client is configured (missing key?)")
        ctx.job.log.log(stage, "openrouter", "unavailable", reason="no API key; using local fallback")
        return None
    try:
        call = ctx.llm.complete_json(stage=stage, system=system, user=user, schema=schema,
                                     prompt_version=prompt_version, **kw)
        return call.data  # type: ignore[return-value]
    except (AuthError, QuotaExhausted, BudgetExceeded, LLMError) as e:
        if ctx.mode == "AI_REQUIRED":
            raise AgentFailure(stage, f"LLM unavailable in AI_REQUIRED mode: {e}") from e
        ctx.job.log.log(stage, "openrouter", "fallback_to_local", error=str(e)[:500])
        ctx.notes.append(f"{stage}: LLM unavailable ({type(e).__name__}); local fallback used")
        if isinstance(e, (AuthError, QuotaExhausted, BudgetExceeded)):
            ctx.llm = None  # do not keep hammering a dead key/quota/budget in later stages
        return None


def words_budget(duration_s: float, mode: str) -> int:
    # calibrated against Edge TTS neural voices at +0% rate (about 140-150 words per minute)
    wpm = 150 if mode != "og" else 140
    # leave ~8% room for pauses between chunks and the closing hold
    return max(12, int(duration_s * 0.92 * wpm / 60))
