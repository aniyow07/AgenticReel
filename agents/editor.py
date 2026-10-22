"""Agent 6: Editor.

Turns the storyboard + measured narration into a validated Remotion timeline,
stages media into the job's public dir, triggers the Remotion render and
finishes the file with FFmpeg (loudness normalisation, spec encode, size cap).
Only known components and validated parameters are used.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agents.base import AgentContext, AgentFailure
from rendering import gpu, manim_runner, remotion_runner
from rendering.media_utils import link_or_copy, measure_loudness, probe, require_tool, run, sha256
from rendering.timeline import (FADE_OUT_S, SEGMENT_GAP_S, NarrationLayout, TimedCaption, build_captions, captions_to_frames,
                                layout_segments, s2f, scene_frames, to_srt)
from schemas.artifacts import AssetManifest, Script, SegmentAudio, Storyboard
from core.themes import pick_palette
import random

from schemas.render_props import BACKDROP_STYLES, CaptionStyle, RenderProps

TARGET_LUFS = -14.0


@dataclass
class OutputProfile:
    width: int
    height: int
    fps: int
    label: str  # "production" | "test"


def output_profile(ctx: AgentContext) -> OutputProfile:
    portrait = ctx.brief.portrait
    if ctx.brief.dev_short:
        return OutputProfile(540 if portrait else 960, 960 if portrait else 540, 30, "test")
    return OutputProfile(1080 if portrait else 1920, 1920 if portrait else 1080, 30, "production")


def video_theme(ctx: AgentContext, name: str | None = None) -> dict:
    return pick_palette(ctx.seed, ctx.brief.topic, name)


def default_caption_style(mode: str, overrides: dict | None = None) -> CaptionStyle:
    base = {"og": dict(fontSize=72, position="lower", animation="fade", uppercase=False, maxWordsPerLine=7,
                       outlineWidth=0, emphasis=0.3),
            "minecraft": dict(fontSize=88, position="center", animation="pop", highlightColor="#FFE135",
                              uppercase=True, maxWordsPerLine=3, outlineWidth=9, emphasis=0.7),
            "subway": dict(fontSize=84, position="center", animation="slide", highlightColor="#2BF0FF",
                           uppercase=True, maxWordsPerLine=3, outlineWidth=8, emphasis=0.6)}[mode]
    base.update(overrides or {})
    return CaptionStyle(**base)


def caption_words(mode: str, style: CaptionStyle) -> int:
    return min(style.maxWordsPerLine * (2 if mode == "og" else 1) + (0 if mode == "og" else 1), 12)


MOTION_INTENSITY = {"off": 0.0, "subtle": 0.5, "auto": 1.0, "strong": 1.6}
MOTION_LEVEL = {"calm": 0, "normal": 1, "strong": 2, "hit": 3}


def assign_backdrops(scenes: list[dict], seed: int, topic: str) -> None:
    """Keep the storyboard's backdrop choice when it gave one; otherwise rotate through a seeded shuffle of the
    styles. Never the same style on two consecutive scenes."""
    rng = random.Random(f"{seed}:{topic}")
    order = list(BACKDROP_STYLES)
    rng.shuffle(order)
    if len(scenes) > 1 and scenes[0].get("visualType") == "title":
        # the intro follows the video's own look: its most used backdrop (not the next scene's, so the cut shows)
        rest = [sc.get("backdrop") for sc in scenes[1:] if sc.get("backdrop") in BACKDROP_STYLES]
        avoid = rest[0] if rest else None
        ranked = sorted(dict.fromkeys(rest), key=lambda s: -rest.count(s))
        scenes[0]["backdrop"] = next((s for s in ranked if s != avoid), next(s for s in order if s != avoid))
    prev = None
    for i, sc in enumerate(scenes):
        style = sc.get("backdrop") if sc.get("backdrop") in BACKDROP_STYLES else order[i % len(order)]
        if style == prev:
            style = next(s for s in order if s != prev)
        sc["backdrop"] = style
        prev = style


def with_motion(frames: list[dict], caps: list[TimedCaption], storyboard: Storyboard) -> list[dict]:
    """Attach the storyboard's per-line motion level to captions. Only the first caption of a line gets the full
    reaction (shake/punch); later phrases of the same line stay at most "normal"."""
    levels: dict[str, int] = {}
    for sc in storyboard.scenes:
        for sid, name in (sc.visual_parameters.get("motion") or {}).items():
            levels[sid] = MOTION_LEVEL.get(name, 1)
    seen: set[str] = set()
    for f, c in zip(frames, caps):
        lvl = levels.get(c.segment_id, 1)
        f["motion"] = lvl if c.segment_id not in seen else min(lvl, 1)
        seen.add(c.segment_id)
    return frames


def compute_layout(segs: list[SegmentAudio]) -> NarrationLayout:
    return layout_segments(segs, gap_s=SEGMENT_GAP_S)


def scene_durations_s(storyboard: Storyboard, layout: NarrationLayout, fps: int) -> dict[str, float]:
    ranges = scene_frames([s.narration_segment_ids for s in storyboard.scenes], layout, fps)
    return {s.scene_id: d / fps for s, (_, d) in zip(storyboard.scenes, ranges)}


def build_timeline(ctx: AgentContext, script: Script, storyboard: Storyboard, manifest: AssetManifest,
                   style_overrides: dict | None = None, show_progress: bool = True, motion: str | None = None,
                   music_volume: float = 0.22) -> tuple[RenderProps, list[TimedCaption]]:
    job, brief = ctx.job, ctx.brief
    prof = output_profile(ctx)
    segs = manifest.segments
    layout = compute_layout(segs)
    total_frames = s2f(layout.total_s, prof.fps)
    style = default_caption_style(brief.mode, style_overrides)
    texts = {s.segment_id: s.text for s in script.segments}
    hls = {s.segment_id: s.highlights for s in script.segments}
    caps = build_captions(texts, segs, layout, max_words=caption_words(brief.mode, style), highlights=hls)
    pub = job.public_dir

    def stage(src: Path, rel: str) -> str:
        link_or_copy(Path(src), pub / rel)
        return rel

    narration = None
    if manifest.narration_path:
        narration = {"src": stage(Path(manifest.narration_path), "audio/narration.wav"), "volume": 1.0}
    music = None
    if manifest.music_path:
        ext = Path(manifest.music_path).suffix.lower() or ".mp3"
        music = {"src": stage(Path(manifest.music_path), f"audio/music{ext}"), "volume": music_volume,
                 "duckedVolume": round(music_volume * 0.3, 3)}

    scenes, background = [], []
    if brief.mode == "og":
        ranges = scene_frames([s.narration_segment_ids for s in storyboard.scenes], layout, prof.fps)
        for sc, (start, dur) in zip(storyboard.scenes, ranges):
            vt, params = sc.visual_type, dict(sc.visual_parameters)
            if vt == "manim":
                rel = manifest.manim_clips.get(sc.scene_id)
                if rel:
                    clip = job.dir / rel
                    heading = params.get("heading", "")
                    if heading.strip().lower() == str((sc.manim_template or {}).get("title", "")).strip().lower():
                        heading = ""  # the Manim clip already shows this title
                    params = {"src": stage(clip, f"manim/{clip.name}"), "heading": heading,
                              "clipDurationInFrames": max(1, int(probe(clip).duration * prof.fps) - 1)}
                else:  # Manim unavailable: compatible Remotion diagram from the same template data
                    alt = manim_runner.remotion_fallback(sc.manim_template or {})
                    if alt:
                        vt, params = alt
                    else:
                        vt, params = "text_reveal", {"text": texts[sc.narration_segment_ids[0]]}
            scenes.append({"id": sc.scene_id, "startFrame": start, "durationInFrames": dur, "visualType": vt,
                           "params": params, "transition": sc.transition, "backdrop": sc.backdrop})
        assign_backdrops(scenes, ctx.seed, brief.topic)
    else:
        if not manifest.background_path:
            raise AgentFailure("editing", "brainrot mode has no prepared gameplay background")
        bg = stage(Path(manifest.background_path), "gameplay/background.mp4")
        background = [{"src": bg, "startFrame": 0, "durationInFrames": total_frames, "trimBeforeFrames": 0}]

    # OG: a palette per video (seed + topic) so reels do not all look alike; transitions vary when the
    # storyboard left them all at the default.
    theme = video_theme(ctx, (style_overrides or {}).get("palette")) if brief.mode == "og" else None
    if scenes and len({s["transition"] for s in scenes}) == 1 and scenes[0]["transition"] == "fade":
        cycle = ["fade", "slide", "zoom"]
        for i, sc in enumerate(scenes):
            sc["transition"] = cycle[i % 3]
    scale = prof.height / 1920 if brief.portrait else prof.height / 1080
    props = RenderProps.model_validate({
        **({"theme": theme} if theme else {}),
        "mode": brief.mode, "fps": prof.fps, "width": prof.width, "height": prof.height,
        "durationInFrames": total_frames, "title": script.title, "narration": narration, "music": music,
        "captions": with_motion(captions_to_frames(caps, prof.fps, total_frames), caps, storyboard),
        "captionStyle": style.model_dump(),
        "scenes": scenes, "background": background, "showProgress": show_progress,
        "motionIntensity": MOTION_INTENSITY[motion or brief.motion],
        "safeZone": {"top": round(250 * scale), "bottom": round(350 * scale)} if brief.portrait else
        {"top": round(60 * scale), "bottom": round(90 * scale)},
    })
    return props, caps


def write_caption_files(ctx: AgentContext, caps: list[TimedCaption]) -> None:
    ctx.job.write_json("captions.json", {"captions": [c.model_dump() for c in caps]})
    ctx.job.write_text("captions.srt", to_srt(caps))


def render(ctx: AgentContext, props: RenderProps) -> remotion_runner.RenderResult:
    job = ctx.job
    res = remotion_runner.render(props, job.public_dir, job.path("render_props.json"),
                                 job.path("render/remotion_raw.mp4"))
    if not res.ok and res.returncode not in (None, 0) and "staged media missing" not in (res.error or ""):
        # Remotion's video compositor occasionally crashes under load; retry once with less parallelism,
        # and on the CPU in case the GPU backend was the problem.
        job.log.log("remotion_render", "remotion", "retry", reason="render failed; retrying with concurrency 2 on the CPU",
                    log_tail=res.log_tail[-600:])
        res = remotion_runner.render(props, job.public_dir, job.path("render_props.json"),
                                     job.path("render/remotion_raw.mp4"), concurrency=2, gpu=False)
    job.log.log("remotion_render", "remotion", "ok" if res.ok else "error", renderer="remotion",
                composition=res.composition, latency_s=round(res.elapsed_s, 2), returncode=res.returncode,
                error=res.error, output=res.output, sha256=res.sha256, probe=res.probe,
                log_tail=res.log_tail[-1500:] if not res.ok else "")
    if not res.ok:
        raise AgentFailure("remotion_render", f"{res.error}\n{res.log_tail[-1500:]}")
    return res


def finish(ctx: AgentContext, raw: Path, props: RenderProps) -> dict:
    """Loudness-normalise (two-pass loudnorm), fade picture and sound out together over the closing tail, encode
    to spec (cut at exactly the timeline length, so audio and video end on the same frame) and enforce the
    size cap."""
    job = ctx.job
    out = job.path("final.mp4")
    has_audio = probe(raw).has_audio
    dur = props.durationInFrames / props.fps
    fade_st = max(0.0, dur - FADE_OUT_S)
    afade = f"afade=t=out:st={fade_st:.3f}:d={FADE_OUT_S}"
    af = ["-af", afade] if has_audio else []
    loud = measure_loudness(raw) if has_audio else None
    if loud and loud.get("input_i") not in (None, "-inf"):
        af = ["-af", (f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:measured_I={loud['input_i']}:"
                      f"measured_TP={loud['input_tp']}:measured_LRA={loud['input_lra']}:"
                      f"measured_thresh={loud['input_thresh']}:offset={loud['target_offset']}:linear=true,"
                      f"aresample=48000,{afade}")]
    vf = ["-vf", f"fade=t=out:st={fade_st:.3f}:d={FADE_OUT_S}"]
    max_mb = ctx.settings.max_output_mb

    use_gpu = gpu.enabled()

    def encode(vflags) -> None:
        """vflags(gpu) gives the video encoder flags; a failed NVENC encode is retried with libx264."""
        nonlocal use_gpu
        for attempt_gpu in ([True, False] if use_gpu else [False]):
            cmd = [require_tool("ffmpeg"), "-v", "error", "-y", "-i", str(raw), *vf, *af, *vflags(attempt_gpu),
                   "-pix_fmt", "yuv420p", "-color_range", "tv", "-r", str(props.fps),
                   "-fps_mode", "cfr", "-t", f"{dur:.3f}", "-movflags", "+faststart"]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
            cmd.append(str(out))
            cp = run(cmd, timeout=1800)
            if cp.returncode == 0 and out.exists():
                job.log.log("ffmpeg", "ffmpeg", "encoded", encoder="h264_nvenc" if attempt_gpu else "libx264")
                return
            if attempt_gpu:
                use_gpu = False
                job.log.log("ffmpeg", "ffmpeg", "retry", reason="NVENC encode failed; retrying with libx264",
                            log_tail=cp.stderr[-600:])
        raise AgentFailure("ffmpeg", f"final encode failed: {cp.stderr[-800:]}")

    encode(lambda g: gpu.h264_args(20, "medium", gpu=g))
    size_mb = out.stat().st_size / 1e6
    attempts = 0
    while size_mb > max_mb and attempts < 2:
        attempts += 1
        dur = probe(out).duration
        vbr = max(300, int((max_mb * 8000 * 0.92) / dur - 170))  # kbps, leaving room for audio + overhead
        job.log.log("ffmpeg", "ffmpeg", "reencode", reason=f"{size_mb:.1f} MB > {max_mb} MB", video_kbps=vbr)
        encode(lambda g, vbr=vbr: gpu.bitrate_args(vbr, gpu=g))
        size_mb = out.stat().st_size / 1e6
    after = measure_loudness(out) if has_audio else None
    info = probe(out)
    result = {"path": str(out), "size_mb": round(size_mb, 2), "sha256": sha256(out), "probe": info.summary(),
              "loudness_before": loud and loud.get("input_i"), "loudness_after": after and after.get("input_i"),
              "true_peak_after": after and after.get("input_tp")}
    job.log.log("ffmpeg", "ffmpeg", "ok", output=out.name, sha256=result["sha256"], size_mb=result["size_mb"],
                loudness_after=result["loudness_after"])
    (job.dir / "render" / "finish.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result

