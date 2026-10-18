"""The user's brief: validated before any job starts."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mode = Literal["og", "minecraft", "subway"]
VideoFormat = Literal["video_9x16", "video_16x9"]
ContentType = Literal["factual_explainer", "promotional", "awareness", "fictional_story", "general_entertainment",
                      "educational_story", "opinion_commentary"]

PROD_MIN_S, PROD_MAX_S = 30, 60
DEV_MIN_S = 5

FACTUAL_TYPES = {"factual_explainer", "promotional", "awareness"}


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", max_length=64)
    topic: str = Field(min_length=3, max_length=1000)
    audience: str = Field(default="General audience", min_length=2, max_length=200)
    mode: Mode = "og"
    duration_s: float = Field(default=45, gt=0, le=180)
    tone: str = Field(default="engaging, clear", max_length=200)
    language: str = Field(default="English", max_length=40)
    subtitle_language: str = Field(default="English", max_length=40)
    format: VideoFormat = "video_9x16"
    content_type: ContentType = "factual_explainer"
    must_include: list[str] = Field(default_factory=list, max_length=20)
    must_avoid: list[str] = Field(default_factory=list, max_length=20)
    cta: str = Field(default="", max_length=200)
    source_files: list[str] = Field(default_factory=list, max_length=20)
    source_text: str = Field(default="", max_length=200_000)
    narration_audio: str = Field(default="", max_length=500)
    # Edge TTS voice short name, e.g. "en-US-GuyNeural"; empty = TTS_VOICE from .env
    voice: str = Field(default="", max_length=60)
    # speaking speed in percent relative to the voice's normal pace (+10 = 10% faster); None = TTS_RATE setting
    speed: int | None = Field(default=None, ge=-30, le=40)
    # brainrot camera motion: "auto" lets the storyboard model pick the energy of each line
    motion: Literal["auto", "off", "subtle", "strong"] = "auto"
    music: str = Field(default="", max_length=500)
    # True only for quick smoke tests; such renders are labelled as test output.
    dev_short: bool = False

    @field_validator("id")
    @classmethod
    def _safe_id(cls, v: str) -> str:
        if v and not re.fullmatch(r"[A-Za-z0-9_\-]+", v):
            raise ValueError("id may contain only letters, digits, '_' and '-'")
        return v

    @field_validator("voice")
    @classmethod
    def _voice(cls, v: str) -> str:
        v = v.strip()
        if v and not re.fullmatch(r"[A-Za-z]{2,3}-[A-Za-z]{2,4}(-[A-Za-z]+)?-[A-Za-z0-9]+Neural", v):
            raise ValueError("voice must be an Edge TTS voice name such as en-US-GuyNeural")
        return v

    @field_validator("topic", "audience", "tone", "cta")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("must_include", "must_avoid")
    @classmethod
    def _items(cls, v: list[str]) -> list[str]:
        out = [s.strip() for s in v if s and s.strip()]
        if any(len(s) > 300 for s in out):
            raise ValueError("each item must be at most 300 characters")
        return out

    @model_validator(mode="after")
    def _duration(self):
        if self.dev_short:
            if self.duration_s < DEV_MIN_S:
                raise ValueError(f"dev-short videos must be at least {DEV_MIN_S}s")
        elif not (PROD_MIN_S <= self.duration_s <= PROD_MAX_S):
            raise ValueError(f"duration_s must be between {PROD_MIN_S} and {PROD_MAX_S} seconds "
                             f"(use dev_short for shorter test renders)")
        return self

    @property
    def is_factual(self) -> bool:
        return self.content_type in FACTUAL_TYPES

    @property
    def portrait(self) -> bool:
        return self.format == "video_9x16"


def load_brief(path: str | Path, **overrides) -> Brief:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("brief YAML must be a mapping")
    data.update({k: v for k, v in overrides.items() if v is not None})
    # Source files in a YAML brief are relative to the brief's folder.
    data["source_files"] = [str((path.parent / s).resolve()) if not Path(s).is_absolute() else s
                            for s in data.get("source_files", []) or []]
    return Brief.model_validate(data)
