"""Pydantic mirror of remotion/src/schemas/props.ts.

Python validates render props before writing render_props.json; Remotion
validates them again with Zod in calculateMetadata.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

VISUAL_TYPES_OG = ("title", "text_reveal", "key_points", "stat", "timeline", "process", "comparison", "chart",
                   "image", "manim", "end_card")
VISUAL_TYPES_BRAINROT = ("gameplay",)
BACKDROP_STYLES = ("orbs", "grid", "waves", "rays", "shapes")


def check_public_path(p: str) -> str:
    if not p or re.match(r"^[a-zA-Z]:", p) or p.startswith(("/", "\\")) or re.match(r"^[a-z]+://", p, re.I):
        raise ValueError(f"media path must be relative to the public directory: {p!r}")
    if ".." in re.split(r"[\\/]", p):
        raise ValueError("path traversal is not allowed")
    return p.replace("\\", "/")


PublicPath = Annotated[str, Field(min_length=1)]


class Caption(BaseModel):
    id: str
    text: str = Field(min_length=1)
    startFrame: int = Field(ge=0)
    endFrame: int = Field(gt=0)
    highlights: list[str] = Field(default_factory=list)
    motion: int = Field(default=1, ge=0, le=3)  # 0 calm, 1 normal, 2 strong, 3 hit


class CaptionStyle(BaseModel):
    fontSize: float = Field(default=72, ge=24, le=160)
    color: str = "#FFFFFF"
    highlightColor: str = "#FFE135"
    outlineColor: str = "#000000"
    outlineWidth: float = Field(default=8, ge=0, le=20)
    position: Literal["upper", "center", "lower"] = "center"
    animation: Literal["pop", "fade", "slide", "none"] = "pop"
    emphasis: float = Field(default=0.6, ge=0, le=1)
    uppercase: bool = True
    maxWordsPerLine: int = Field(default=4, ge=1, le=10)


class _SrcModel(BaseModel):
    @field_validator("src", check_fields=False)
    @classmethod
    def _src(cls, v: str) -> str:
        return check_public_path(v)


class AudioTrack(_SrcModel):
    src: str
    volume: float = Field(default=1, ge=0, le=2)


class Music(_SrcModel):
    src: str
    volume: float = Field(default=0.25, ge=0, le=1)
    duckedVolume: float = Field(default=0.08, ge=0, le=1)


# ---- OG scene params ----
class TitleParams(BaseModel):
    title: str
    subtitle: str = ""


class TextRevealParams(BaseModel):
    text: str


class KeyPointsParams(BaseModel):
    heading: str = ""
    points: list[str] = Field(min_length=1, max_length=6)


class StatParams(BaseModel):
    value: float
    prefix: str = ""
    suffix: str = ""
    label: str
    sourceNote: str = ""


class TimelineEvent(BaseModel):
    label: str
    detail: str = ""


class TimelineParams(BaseModel):
    heading: str = ""
    events: list[TimelineEvent] = Field(min_length=2, max_length=6)


class ProcessParams(BaseModel):
    heading: str = ""
    steps: list[str] = Field(min_length=2, max_length=6)


class ComparisonParams(BaseModel):
    heading: str = ""
    leftTitle: str
    rightTitle: str
    leftPoints: list[str] = Field(min_length=1, max_length=5)
    rightPoints: list[str] = Field(min_length=1, max_length=5)


class ChartParams(BaseModel):
    heading: str = ""
    labels: list[str] = Field(min_length=1, max_length=8)
    values: list[float] = Field(min_length=1, max_length=8)
    unit: str = ""
    sourceNote: str = ""

    @model_validator(mode="after")
    def _len(self):
        if len(self.labels) != len(self.values):
            raise ValueError("chart labels and values must have the same length")
        return self


class ImageParams(_SrcModel):
    src: str
    caption: str = ""


class ManimParams(_SrcModel):
    src: str
    heading: str = ""
    clipDurationInFrames: int | None = Field(default=None, gt=0)


class EndCardParams(BaseModel):
    text: str
    cta: str = ""


PARAM_MODELS: dict[str, type[BaseModel]] = {
    "title": TitleParams, "text_reveal": TextRevealParams, "key_points": KeyPointsParams, "stat": StatParams,
    "timeline": TimelineParams, "process": ProcessParams, "comparison": ComparisonParams, "chart": ChartParams,
    "image": ImageParams, "manim": ManimParams, "end_card": EndCardParams,
}


class Scene(BaseModel):
    id: str
    startFrame: int = Field(ge=0)
    durationInFrames: int = Field(gt=0)
    transition: Literal["fade", "slide", "zoom", "none"] = "fade"
    backdrop: Literal[BACKDROP_STYLES] = "orbs"  # type: ignore[valid-type]
    visualType: Literal[VISUAL_TYPES_OG]  # type: ignore[valid-type]
    params: dict

    @model_validator(mode="after")
    def _params(self):
        self.params = PARAM_MODELS[self.visualType].model_validate(self.params).model_dump()
        return self


class BackgroundSegment(_SrcModel):
    src: str
    startFrame: int = Field(ge=0)
    durationInFrames: int = Field(gt=0)
    trimBeforeFrames: int = Field(default=0, ge=0)


class Theme(BaseModel):
    name: str = "default"
    background: str = "#0B1020"
    surface: str = "#151C33"
    primary: str = "#7C9CFF"
    accent: str = "#FFB547"
    text: str = "#F5F7FF"
    mutedText: str = "#A9B2D0"
    fontFamily: str = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


class SafeZone(BaseModel):
    top: int = Field(ge=0)
    bottom: int = Field(ge=0)


class RenderProps(BaseModel):
    mode: Literal["og", "minecraft", "subway"]
    fps: int = Field(ge=10, le=60)
    width: int = Field(ge=160, le=3840)
    height: int = Field(ge=160, le=3840)
    durationInFrames: int = Field(gt=0)
    title: str = ""
    narration: AudioTrack | None = None
    music: Music | None = None
    captions: list[Caption] = Field(default_factory=list)
    captionStyle: CaptionStyle = Field(default_factory=CaptionStyle)
    showCaptions: bool = True
    scenes: list[Scene] = Field(default_factory=list)
    background: list[BackgroundSegment] = Field(default_factory=list)
    showProgress: bool = True
    zoomEffects: bool = True
    motionIntensity: float = Field(default=1.0, ge=0, le=2)
    theme: Theme = Field(default_factory=Theme)
    safeZone: SafeZone = Field(default_factory=lambda: SafeZone(top=250, bottom=350))

    @model_validator(mode="after")
    def _consistency(self):
        for c in self.captions:
            if c.endFrame <= c.startFrame:
                raise ValueError(f"caption {c.id} ends before it starts")
            if c.endFrame > self.durationInFrames:
                raise ValueError(f"caption {c.id} extends past the video end")
        for s in self.scenes:
            if s.startFrame + s.durationInFrames > self.durationInFrames:
                raise ValueError(f"scene {s.id} extends past the video end")
        if self.mode != "og" and not self.background:
            raise ValueError(f"{self.mode} mode requires at least one gameplay background segment")
        if self.mode == "og" and not self.scenes:
            raise ValueError("og mode requires at least one scene")
        return self

    def media_paths(self) -> list[str]:
        paths = [t.src for t in (self.narration, self.music) if t]
        paths += [b.src for b in self.background]
        paths += [s.params["src"] for s in self.scenes if s.visualType in ("image", "manim")]
        return paths


COMPOSITION_FOR_MODE = {"og": "OGVideo", "minecraft": "MinecraftBrainrot", "subway": "SubwayBrainrot"}

