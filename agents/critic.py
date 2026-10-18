"""Agent 7: Critic / QA -> qa_report.json

Deterministic media and content checks, plus an optional LLM semantic review.
A technical pass (valid, on-spec file) is reported separately from semantic
approval, and test renders are labelled as such.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agents.base import AgentContext, ask_llm, brief_summary
from agents.editor import output_profile
from agents.scriptwriter import check_script
from core.mathtext import KEEP_KEYS, has_raw_latex
from rendering.media_utils import MediaError, black_frame_ratio, probe
from rendering.timeline import parse_srt
from schemas.artifacts import AssetManifest, Facts, QACheck, QAReport, Script, Storyboard
from schemas.brief import PROD_MAX_S, PROD_MIN_S
from schemas.render_props import RenderProps

PROMPT_VERSION = "critic/v1"


class SemanticLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    verdict: str = Field(pattern="^(approved|needs_changes)$")
    issues: list[str] = Field(default_factory=list, max_length=8)


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


def _stems(s: str) -> set[str]:
    from retrieval.index import tokenize
    return set(tokenize(s))


def run(ctx: AgentContext, script: Script, storyboard: Storyboard, facts: Facts, manifest: AssetManifest,
        props: RenderProps, repairs: int = 0, semantic: bool = True) -> QAReport:
    job, brief = ctx.job, ctx.brief
    prof = output_profile(ctx)
    checks: list[QACheck] = []

    def check(name, ok, detail="", severity="error", route=None):
        checks.append(QACheck(name=name, passed=bool(ok), severity=severity, detail=detail,
                              route_to=None if ok else route))

    final = job.path("final.mp4")
    info = None
    try:
        info = probe(final)
        check("final_mp4_valid", info.has_video, f"{info.format_name}, {info.size_bytes} bytes", route="ffmpeg")
    except MediaError as e:
        check("final_mp4_valid", False, str(e), route="remotion_render")
    expected_s = props.durationInFrames / props.fps
    if info:
        check("video_codec_h264", info.video_codec == "h264", str(info.video_codec), route="ffmpeg")
        check("pixel_format_yuv420p", info.pix_fmt == "yuv420p", str(info.pix_fmt), route="ffmpeg")
        check("resolution", (info.width, info.height) == (prof.width, prof.height),
              f"{info.width}x{info.height}, expected {prof.width}x{prof.height}", route="remotion_render")
        check("frame_rate", info.fps is not None and abs(info.fps - prof.fps) < 0.01, f"{info.fps}", route="ffmpeg")
        check("audio_stream_aac_48k_stereo", info.audio_codec == "aac" and info.sample_rate == 48000 and
              info.channels == 2, f"{info.audio_codec} {info.sample_rate} Hz {info.channels} ch", route="ffmpeg")
        check("duration_matches_timeline", abs(info.duration - expected_s) < 0.3,
              f"{info.duration:.2f}s vs timeline {expected_s:.2f}s", route="remotion_render")
        if brief.dev_short:
            check("duration_target", True, f"{info.duration:.1f}s TEST render (dev-short), not a production-length "
                                           f"video", severity="info")
        else:
            check("duration_target", PROD_MIN_S - 0.5 <= info.duration <= PROD_MAX_S + 0.5,
                  f"{info.duration:.1f}s (allowed {PROD_MIN_S}-{PROD_MAX_S}s, brief asked {brief.duration_s:.0f}s)",
                  route="scripting")
            check("duration_close_to_brief", abs(info.duration - brief.duration_s) <= max(6, brief.duration_s * 0.15),
                  f"{info.duration:.1f}s vs {brief.duration_s:.0f}s", severity="warning", route="scripting")
        size_mb = info.size_bytes / 1e6
        check("file_size", size_mb <= ctx.settings.max_output_mb, f"{size_mb:.1f} MB", route="ffmpeg")
        try:
            blk = black_frame_ratio(final, threshold=0.98)
            check("no_black_frames", blk < 0.03, f"{blk * 100:.1f}% black", route="remotion_render")
        except MediaError as e:
            check("no_black_frames", False, str(e), severity="warning")
    fin = job.dir / "render" / "finish.json"
    if fin.exists():
        import json

        f = json.loads(fin.read_text(encoding="utf-8"))
        lufs = f.get("loudness_after")
        try:
            lv = float(lufs)
            check("loudness_about_-14_LUFS", abs(lv + 14) <= 2, f"{lv:.1f} LUFS", severity="warning", route="ffmpeg")
            check("audio_intelligible", lv > -30, f"{lv:.1f} LUFS integrated", route="tts")
        except (TypeError, ValueError):
            check("audio_intelligible", False, f"loudness unavailable ({lufs})", route="tts")

    # captions
    srt = job.path("captions.srt")
    check("srt_saved", srt.exists() and srt.stat().st_size > 0, str(srt.name), route="editing")
    caps = props.captions
    ok_ranges = all(0 <= c.startFrame < c.endFrame <= props.durationInFrames for c in caps)
    no_overlap = all(a.endFrame <= b.startFrame for a, b in zip(caps, caps[1:]))
    check("caption_ranges_valid", ok_ranges and no_overlap and bool(caps),
          f"{len(caps)} captions, ordered and non-overlapping" if ok_ranges and no_overlap else "invalid ranges",
          route="editing")
    cap_text = _norm(" ".join(c.text for c in caps))
    narr_text = _norm(" ".join(s.text for s in script.segments))
    check("captions_match_narration", cap_text == narr_text,
          "caption text equals the narration script" if cap_text == narr_text else "caption text differs from "
          "script", route="editing")
    if srt.exists():
        srt_items = parse_srt(srt.read_text(encoding="utf-8"))
        check("srt_matches_burned_captions", len(srt_items) == len(caps), f"{len(srt_items)} SRT cues",
              route="editing")
    aligns = {c.alignment for c in _caption_alignments(job)}
    check("caption_alignment_source", "proportional_within_measured_segment" not in aligns and
          "supplied_audio" not in aligns, f"alignment: {sorted(aligns)}", severity="warning")
    min_font = 48 * props.width / 1080
    # mirrors the compositions: OG uses max(48px, 0.7 * fontSize) scaled to the width; brainrot uses fontSize
    eff_font = (max(min_font, props.captionStyle.fontSize * 0.7 * props.width / 1080) if props.mode == "og"
                else props.captionStyle.fontSize * props.width / 1080)
    check("caption_readable_size", eff_font >= min_font * 0.99, f"{eff_font:.0f}px (min {min_font:.0f}px)",
          route="editing")
    check("captions_within_safe_zone", props.safeZone.top > 0 and props.safeZone.bottom > 0,
          f"safe zone top {props.safeZone.top}px / bottom {props.safeZone.bottom}px", severity="warning")
    # speech coverage: every narration segment has at least one caption
    seg_ids = {s.segment_id for s in script.segments}
    covered = {c.segment_id for c in _caption_alignments(job)}
    check("every_segment_captioned", seg_ids <= covered, f"{len(covered)}/{len(seg_ids)} segments", route="editing")

    # equations must reach the screen as math, never as raw LaTeX commands
    raw = [t for t in _screen_texts(props) if has_raw_latex(t)]
    check("no_raw_latex_on_screen", not raw, f"raw LaTeX in: {raw[0][:60]!r}" if raw else "clean",
          route="storyboarding")

    # scenes
    if props.mode == "og":
        tiles = sorted((s.startFrame, s.durationInFrames) for s in props.scenes)
        t, ok = 0, True
        for st, d in tiles:
            ok &= st == t
            t = st + d
        ok &= t == props.durationInFrames
        check("scenes_cover_timeline", ok, f"{len(tiles)} scenes", route="storyboarding")
        check("required_scenes_present", len(props.scenes) >= 2 and props.scenes[0].visualType == "title",
              f"first scene: {props.scenes[0].visualType if props.scenes else 'none'}", severity="warning",
              route="storyboarding")
        manim_planned = [s for s in storyboard.scenes if s.visual_type == "manim"]
        manim_used = [s for s in props.scenes if s.visualType == "manim"]
        if manim_planned:
            check("manim_clips_rendered", len(manim_used) == len(manim_planned),
                  f"{len(manim_used)}/{len(manim_planned)} Manim scenes rendered", severity="warning", route="manim")
    else:
        check("real_gameplay_background", bool(manifest.gameplay_clip_ids) and bool(props.background),
              f"clips: {manifest.gameplay_clip_ids}", route="assets")
        statuses = [a.review_status for a in manifest.assets if a.kind == "gameplay"]
        check("gameplay_not_rejected", "rejected" not in statuses, f"review statuses: {statuses}", route="assets")
        check("gameplay_permission_verified", statuses and all(s == "verified" for s in statuses),
              "gameplay permission not verified; see assets/manifest.csv" if any(s != "verified" for s in statuses)
              else "verified", severity="warning")
    check("assets_present", not manifest.missing, f"missing: {manifest.missing}" if manifest.missing else "all present",
          route="assets")

    # content
    issues = check_script(script, facts, ctx)
    fact_issues = [i for i in issues if "fact" in i or "number" in i]
    check("claims_supported", not fact_issues, "; ".join(fact_issues) or "no unsupported claims found",
          route="scripting")
    if brief.is_factual:
        check("has_verified_sources", bool(facts.supported()),
              "no verified facts; video is general" if not facts.supported() else
              f"{len(facts.supported())} supported/user facts", severity="warning")
    avoid = [i for i in issues if "avoid" in i]
    check("respects_must_avoid", not avoid, "; ".join(avoid), route="scripting")
    low = " ".join(s.text.lower() for s in script.segments)
    missing_inc = [m for m in brief.must_include if not set(_norm(m).split()[:3]) <= set(_norm(low).split())]
    check("covers_must_include", not missing_inc, f"not clearly covered: {missing_inc}" if missing_inc else "ok",
          severity="warning", route="scripting")
    topic_words = sorted(_stems(brief.topic))
    narr = _stems(low)
    hit = sum(1 for w in topic_words if w in narr)
    check("addresses_brief_topic", not topic_words or hit / len(topic_words) >= 0.3,
          f"{hit}/{len(topic_words)} topic words in narration", severity="warning", route="scripting")
    logs_ok = job.log.run_log.exists() and job.log.cost_csv.exists()
    check("logs_saved", logs_ok, "run_log.jsonl and cost_report.csv", severity="warning")

    technical = all(c.passed for c in checks if c.severity == "error")
    semantic_status, notes = "not_reviewed", []
    if semantic and technical and ctx.llm_enabled():
        user = (f"Brief: {brief_summary(brief)}\n\nScript:\n" + "\n".join(s.text for s in script.segments) +
                f"\n\nSupported facts: {[f.claim for f in facts.supported()]}\nLimitations: {facts.limitations}\n"
                "Does this narration address the brief for its audience and read naturally? Check every sentence against "
                "the supported facts: flag any claim that is not in them, any merged or misattributed facts (e.g. an "
                "achievement credited to the wrong job or project) and any invented skills or numbers. Return JSON {\"verdict\": \"approved\"|\"needs_changes\", \"issues\": [...]}")
        sem = ask_llm(ctx, "qa", "You are the Critic agent. Review strictly but fairly.", user, SemanticLLM,
                      PROMPT_VERSION, temperature=0.1, max_tokens=800)
        if sem:
            semantic_status, notes = sem.verdict, sem.issues
    return QAReport(technical_pass=technical, semantic_status=semantic_status, checks=checks, semantic_notes=notes,
                    repairs_attempted=repairs, is_test_render=brief.dev_short,
                    output={"final": str(final), "srt": str(srt), "duration_s": info.duration if info else None,
                            "label": "TEST RENDER (dev-short)" if brief.dev_short else "production"})


def _screen_texts(props) -> list[str]:
    """Every string shown on screen: scene parameters, Manim params and captions."""
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in KEEP_KEYS:
                    walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    data = props.model_dump() if hasattr(props, "model_dump") else {}
    walk(data.get("scenes", []))
    walk([c.get("text", "") for c in data.get("captions", []) or [] if isinstance(c, dict)])
    return out


def _caption_alignments(job):
    from rendering.timeline import TimedCaption

    p = job.path("captions.json")
    if not p.exists():
        return []
    import json

    return [TimedCaption(**c) for c in json.loads(p.read_text(encoding="utf-8"))["captions"]]

