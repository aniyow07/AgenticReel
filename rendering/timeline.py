"""Deterministic timeline maths: narration placement, captions, scene frames and SRT.

All timings come from *measured* audio. Word-level timings from the TTS engine
are used when available; otherwise a segment's measured duration is shared
between its phrases by character count (never the whole video split evenly).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from schemas.artifacts import SegmentAudio

SEGMENT_GAP_S = 0.12  # pause inserted between narration chunks
TAIL_S = 0.6  # hold after the last word


class TimedCaption(BaseModel):
    id: str
    text: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    segment_id: str
    highlights: list[str] = Field(default_factory=list)
    alignment: str  # "tts_word_boundaries" | "proportional_within_measured_segment" | "supplied_audio"


class SegmentPlacement(BaseModel):
    segment_id: str
    start: float
    end: float


@dataclass
class NarrationLayout:
    placements: list[SegmentPlacement]
    total_s: float


def s2f(seconds: float, fps: int) -> int:
    return int(round(seconds * fps))


def layout_segments(segments: list[SegmentAudio], gap_s: float = SEGMENT_GAP_S, tail_s: float = TAIL_S,
                    lead_s: float = 0.0) -> NarrationLayout:
    t = lead_s
    out = []
    for i, seg in enumerate(segments):
        out.append(SegmentPlacement(segment_id=seg.segment_id, start=t, end=t + seg.duration_s))
        t += seg.duration_s + (gap_s if i < len(segments) - 1 else 0)
    return NarrationLayout(placements=out, total_s=t + tail_s)


_WORD = re.compile(r"\S+")


def _phrases(words: list[str], max_words: int) -> list[list[int]]:
    """Group word indexes into short phrases, breaking at punctuation where possible."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        end_punct = bool(re.search(r"[.!?;:,]$", w))
        if len(cur) >= max_words or (end_punct and len(cur) >= max(2, max_words // 2)) or re.search(r"[.!?]$", w):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    # Never leave a one-word caption ("IT."): fold it into a neighbour.
    merged: list[list[int]] = []
    for g in groups:
        if len(g) == 1 and merged and len(merged[-1]) <= max_words:
            merged[-1].extend(g)
        else:
            merged.append(g)
    if len(merged) > 1 and len(merged[0]) == 1:
        merged[1] = merged[0] + merged[1]
        merged.pop(0)
    return merged


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def build_captions(segment_texts: dict[str, str], segments: list[SegmentAudio], layout: NarrationLayout,
                   max_words: int = 4, highlights: dict[str, list[str]] | None = None) -> list[TimedCaption]:
    highlights = highlights or {}
    place = {p.segment_id: p for p in layout.placements}
    caps: list[TimedCaption] = []
    for seg in segments:
        p = place[seg.segment_id]
        words = _WORD.findall(segment_texts[seg.segment_id])
        if not words:
            continue
        timings: list[tuple[float, float]] | None = None
        wt = seg.word_timings
        if wt and len(wt) == len(words):
            timings = [(s, e) for _, s, e in wt]
        elif wt:
            # Align by normalised text when counts differ (e.g. TTS merged "e.g." tokens).
            spoken = [(_norm(w), s, e) for w, s, e in wt]
            timings, j = [], 0
            for w in words:
                n = _norm(w)
                k = next((x for x in range(j, min(j + 4, len(spoken))) if spoken[x][0] == n), None)
                if k is None:
                    timings = None
                    break
                timings.append((spoken[k][1], spoken[k][2]))
                j = k + 1
        for g in _phrases(words, max_words):
            text = " ".join(words[i] for i in g)
            if timings:
                start, end = timings[g[0]][0], timings[g[-1]][1]
                align = "tts_word_boundaries"
            else:
                total_chars = sum(len(w) + 1 for w in words)
                before = sum(len(words[i]) + 1 for i in range(g[0]))
                inside = sum(len(words[i]) + 1 for i in g)
                start = seg.duration_s * before / total_chars
                end = seg.duration_s * (before + inside) / total_chars
                align = "supplied_audio" if seg.provider == "supplied" else "proportional_within_measured_segment"
            hl = [h for h in highlights.get(seg.segment_id, []) if any(_norm(h.split()[0]) == _norm(words[i])
                                                                        for i in g if h.split())]
            caps.append(TimedCaption(id=f"cap{len(caps) + 1:03d}", text=text, start=round(p.start + start, 3),
                                     end=round(p.start + max(end, start + 0.2), 3), segment_id=seg.segment_id,
                                     highlights=hl, alignment=align))
    # Close small gaps so captions do not flicker between phrases; never overlap.
    for a, b in zip(caps, caps[1:]):
        if b.start - a.end < 0.35:
            a.end = max(a.start + 0.1, b.start)
        if a.end > b.start:
            a.end = b.start
    return caps


def captions_to_frames(caps: list[TimedCaption], fps: int, total_frames: int) -> list[dict]:
    out = []
    for c in caps:
        sf = min(s2f(c.start, fps), total_frames - 1)
        ef = min(max(s2f(c.end, fps), sf + 1), total_frames)
        out.append({"id": c.id, "text": c.text, "startFrame": sf, "endFrame": ef, "highlights": c.highlights})
    # Rounding can create 1-frame overlaps; clip them.
    for a, b in zip(out, out[1:]):
        if a["endFrame"] > b["startFrame"]:
            a["endFrame"] = max(a["startFrame"] + 1, b["startFrame"])
    return out


def scene_frames(scene_segments: list[list[str]], layout: NarrationLayout, fps: int) -> list[tuple[int, int]]:
    """Frame ranges that tile [0, total) exactly. Scene i starts where its first segment starts."""
    place = {p.segment_id: p for p in layout.placements}
    total = s2f(layout.total_s, fps)
    starts = [0] + [s2f(place[ids[0]].start, fps) for ids in scene_segments[1:]]
    ranges = []
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else total
        if end <= st:
            raise ValueError(f"scene {i} would have no duration")
        ranges.append((st, end - st))
    return ranges


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(caps: list[TimedCaption]) -> str:
    blocks = [f"{i}\n{_ts(c.start)} --> {_ts(c.end)}\n{c.text}\n" for i, c in enumerate(caps, 1)]
    return "\n".join(blocks)


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", lines[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        out.append((s, e, " ".join(lines[2:])))
    return out
