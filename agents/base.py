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
from rendering.timeline import TAIL_S
from schemas.brief import PROD_MAX_S, PROD_MIN_S, Brief

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
    # word count asked of a rewrite after the narration missed the length window (job.state "words_target")
    words_target: int | None = None

    @property
    def base_rate(self) -> str:
        """The speaking speed asked for: the brief's speed if set, else TTS_RATE from settings."""
        if self.brief.speed is not None:
            return f"{self.brief.speed:+d}%"
        return self.settings.tts_rate

    @property
    def tts_rate(self) -> str:
        return self.rate_override or self.base_rate

    @property
    def speed_pct(self) -> int:
        return rate_pct(self.base_rate)

    @property
    def pace(self) -> float:
        """Chatterbox-Turbo speaks about 158-175 words a minute at its normal speed (mean 165 over four 45-60 s
        jobs, 2026-10-21), about 1.18x the Edge voices the word budget was calibrated on."""
        return 1.18 if self.tts_provider == "chatterbox" else 1.0

    @property
    def tts_provider(self) -> str:
        """The voice engine for this video: the brief's choice (Create screen, --tts-engine), else TTS_ENGINE."""
        return getattr(self.brief, "tts_engine", "") or getattr(self.settings, "tts_provider", "")

    @property
    def word_budget(self) -> int:
        """Words the script should have: the rewrite target after a length miss, else words_budget()."""
        return self.words_target or words_budget(self.brief.duration_s, self.brief.mode, self.speed_pct, self.pace)

    @property
    def voice(self) -> str:
        """The brief's voice if it belongs to this video's engine (Edge names end in "Neural"), else that engine's
        default voice."""
        edge = self.tts_provider != "chatterbox"
        v = self.brief.voice
        if v and v.endswith("Neural") == edge:
            return v
        if self.tts_provider == getattr(self.settings, "tts_provider", ""):
            return self.settings.tts_voice
        return getattr(self.settings, "edge_voice" if edge else "chatterbox_voice", "") or self.settings.tts_voice

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


def rate_pct(rate: str) -> int:
    """'+10%' -> 10, '-5%' -> -5; anything unreadable counts as 0."""
    try:
        return int(str(rate).strip().rstrip("%") or 0)
    except ValueError:
        return 0


def length_window(target_s: float) -> tuple[float, float]:
    """The final lengths accepted for a requested length: within 3 s of it, but never outside the 30-60 s a
    full video must have (so 30 -> 30-33, 45 -> 42-48, 60 -> 57-60). Test renders just get +/-3 s."""
    lo, hi = max(PROD_MIN_S, target_s - 3), min(PROD_MAX_S, target_s + 3)
    return (lo, hi) if lo < hi else (max(1.0, target_s - 3), target_s + 3)


def length_aim(target_s: float) -> float:
    """The length the narration is fitted to: the middle of the window."""
    lo, hi = length_window(target_s)
    return (lo + hi) / 2


def words_budget(duration_s: float, mode: str, speed_pct: int = 0, pace: float = 1.0) -> int:
    # calibrated against Edge TTS neural voices at +0% rate (about 140-150 words per minute); a faster voice
    # needs proportionally more words to fill the same time, so videos do not come out short.
    # `pace` is the engine's natural speed relative to that (AgentContext.pace).
    wpm = (150 if mode != "og" else 140) * (1 + speed_pct / 100) * pace
    # speech fills the aimed length minus the closing tail and the short pauses between chunks (~2%)
    speech_s = length_aim(duration_s) * 0.98 - TAIL_S
    return max(12, int(speech_s * wpm / 60))
