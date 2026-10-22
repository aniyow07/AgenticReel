"""Agent 5: Asset Generator.

Prepares narration (per-chunk TTS with measured durations), real gameplay
backgrounds, permitted music and trusted Manim clips, and records everything in
assets/manifest.json. Nothing is reported as generated unless the file exists
and validates.
"""
from __future__ import annotations

import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agents.base import AgentContext, AgentFailure
from core import gameplay
from providers import tts as tts_mod
from rendering import gpu, manim_runner
from rendering.media_utils import MediaError, link_or_copy, probe, require_tool, run, sha256
from schemas.artifacts import AssetEntry, AssetManifest, Script, SegmentAudio, Storyboard

XFADE_S = 0.25
MIDDLE_MARGIN = 0.15  # skip the first/last 15% of each clip
MANIM_WORKERS = 4  # Manim clips rendered at once
MIN_CUT_S, MAX_CUT_S = 4.0, 7.0  # background cuts to a new stretch this often


def _h(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


# ---------------- narration ----------------
def synthesize_segments(ctx: AgentContext, script: Script) -> list[SegmentAudio]:
    job, s = ctx.job, ctx.settings
    out_dir = job.assets_dir / "audio"
    if ctx.brief.narration_audio:
        return _supplied_segments(ctx, script)
    chain = tts_mod.provider_chain(ctx.tts_provider, ctx.voice, ctx.tts_rate, ctx.mode == "LOCAL_ONLY")
    if not chain:
        if ctx.tts_provider == "chatterbox":
            raise AgentFailure("tts", "No TTS backend is available: the Chatterbox voice needs .venv-tts and the model files in "
                                      f"{tts_mod.chatterbox_model_dir()}. Supply narration audio instead.")
        raise AgentFailure("tts", "No TTS backend is available (edge-tts and Windows SAPI both unavailable). "
                                  "Supply narration audio instead.")
    results: list[SegmentAudio] = []
    for seg in script.segments:
        wav = out_dir / f"{seg.segment_id}.wav"
        meta = wav.with_suffix(".json")
        key = _h(seg.text, [p.name for p in chain], ctx.voice, ctx.tts_rate)
        if wav.exists() and meta.exists():
            m = json.loads(meta.read_text(encoding="utf-8"))
            if m.get("key") == key:
                try:
                    if abs(probe(wav).duration - m["duration_s"]) < 0.05:
                        results.append(SegmentAudio(**m["segment"]))
                        job.log.log("tts", m["segment"]["provider"], "cached", segment=seg.segment_id)
                        continue
                except MediaError:
                    pass
        last_err = None
        for prov in chain:
            try:
                r = prov.synthesize(seg.text, wav)
                sa = SegmentAudio(segment_id=seg.segment_id, path=str(wav.relative_to(job.dir)),
                                  duration_s=round(r.duration_s, 4), word_timings=r.word_timings, provider=r.provider)
                meta.write_text(json.dumps({"key": key, "duration_s": r.duration_s, "segment": sa.model_dump()}),
                                encoding="utf-8")
                job.log.log("tts", r.provider, "ok", segment=seg.segment_id, voice=r.voice,
                            duration_s=round(r.duration_s, 3), latency_s=round(r.elapsed_s, 3),
                            word_timings=len(r.word_timings), output=str(wav.name), sha256=sha256(wav),
                            **getattr(r, "stats", {}))
                results.append(sa)
                break
            except tts_mod.TTSError as e:
                last_err = e
                job.log.log("tts", prov.name, "error", segment=seg.segment_id, error=str(e)[:400])
        else:
            raise AgentFailure("tts", f"all TTS providers failed for {seg.segment_id}: {last_err}")
    providers = {r.provider for r in results}
    if len(providers) > 1:
        ctx.notes.append(f"Narration mixes TTS providers {sorted(providers)} because one failed mid-job.")
    return results


def _supplied_segments(ctx: AgentContext, script: Script) -> list[SegmentAudio]:
    """User narration: one file for the whole script. Segment times are shared by character count
    within the *measured* file duration and flagged as approximate."""
    job = ctx.job
    wav = job.assets_dir / "audio" / "supplied.wav"
    r = tts_mod.prepare_supplied_audio(Path(ctx.brief.narration_audio), wav)
    chars = [len(s.text) for s in script.segments]
    total = sum(chars)
    out, t = [], 0.0
    for seg, c in zip(script.segments, chars):
        d = r.duration_s * c / total
        out.append(SegmentAudio(segment_id=seg.segment_id, path=str(wav.relative_to(job.dir)), duration_s=d,
                                provider="supplied"))
        t += d
    job.log.log("tts", "supplied", "ok", duration_s=r.duration_s, note="segment times approximated by characters")
    ctx.notes.append("Supplied narration: caption timing is approximate (shared by text length within the measured "
                     "audio), not word-aligned.")
    return out


def add_pauses(ctx: AgentContext, segs: list[SegmentAudio], pause_s: float) -> list[SegmentAudio]:
    """Lengthen the pause after every chunk but the last by `pause_s` (silence appended to a copy of the chunk),
    so narration a little short of the requested length fills it without slowing the voice further."""
    job, out = ctx.job, []
    for i, s in enumerate(segs):
        if i == len(segs) - 1 or pause_s <= 0:
            out.append(s)
            continue
        src = job.dir / s.path
        dst = src.with_name(src.stem + "_p.wav")
        cp = run([require_tool("ffmpeg"), "-v", "error", "-y", "-i", str(src), "-af", f"apad=pad_dur={pause_s:.3f}",
                  "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(dst)])
        if cp.returncode != 0 or not dst.exists():
            raise AgentFailure("tts", f"could not add a pause after {s.segment_id}: {cp.stderr[:300]}")
        out.append(s.model_copy(update={"path": str(dst.relative_to(job.dir)), "duration_s": probe(dst).duration}))
    return out


def assemble_narration(ctx: AgentContext, segs: list[SegmentAudio], gap_s: float) -> Path:
    job = ctx.job
    out = job.assets_dir / "audio" / "narration.wav"
    if segs and all(s.provider == "supplied" for s in segs):
        link_or_copy(job.dir / segs[0].path, out)
        return out
    silence = job.assets_dir / "audio" / "_gap.wav"
    cp = run([require_tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
              "anullsrc=r=48000:cl=stereo", "-t", f"{gap_s:.3f}", "-c:a", "pcm_s16le", str(silence)])
    if cp.returncode != 0:
        raise AgentFailure("tts", f"could not create silence: {cp.stderr[:300]}")
    lst = job.assets_dir / "audio" / "_concat.txt"
    lines = []
    for i, s in enumerate(segs):
        lines.append(f"file '{(job.dir / s.path).as_posix()}'")
        if i < len(segs) - 1:
            lines.append(f"file '{silence.as_posix()}'")
    lst.write_text("\n".join(lines), encoding="utf-8")
    cp = run([require_tool("ffmpeg"), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
              "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(out)])
    if cp.returncode != 0 or not out.exists():
        raise AgentFailure("tts", f"could not assemble narration: {cp.stderr[:300]}")
    expected = sum(s.duration_s for s in segs) + gap_s * (len(segs) - 1)
    got = probe(out).duration
    if abs(got - expected) > 0.25:
        raise AgentFailure("tts", f"assembled narration is {got:.2f}s but chunks add up to {expected:.2f}s")
    return out


# ---------------- gameplay ----------------
def prepare_gameplay(ctx: AgentContext, total_s: float, width: int, height: int, fps: int) -> tuple[Path, list[str]]:
    """Build one muted background clip of exactly total_s from real gameplay clips:
    random (seeded) start, concatenation/looping with short crossfades, cover-scale and centre crop."""
    game = ctx.brief.mode
    try:
        clips = gameplay.select_clips(game, total_s, seed=ctx.seed)
    except gameplay.GameplayUnavailable as e:
        raise AgentFailure("assets", str(e)) from e
    rng = random.Random(f"{ctx.seed}:{ctx.job.id}")
    # One clip per video, picked at random (each clip equally likely, whatever its length), so videos alternate
    # between the available footage. The pick is stable for the job, so resuming re-uses the same clip.
    clips = [rng.choice(sorted(clips, key=lambda c: c.record.asset_id))]
    ctx.job.log.log("assets", "gameplay", "clip_chosen", asset_id=clips[0].record.asset_id,
                    candidates=len(gameplay.usable_clips(game, deep=False)))
    # Pure-gameplay windows from every usable clip (menus/intros excluded via usable_ranges).
    # Prefer the middle of each clip (openings often show menus/inventory set-up, endings show outros).
    windows = []
    for c in clips:
        dur = c.duration_s or 0
        lo, hi = dur * MIDDLE_MARGIN, dur * (1 - MIDDLE_MARGIN)
        for a, b in c.record.windows():
            a2, b2 = max(a, lo), min(b, hi)
            if b2 - a2 >= MIN_CUT_S:
                windows.append((c, a2, b2))
    if not windows:  # very short clips: fall back to the whole usable ranges
        windows = [(c, a, b) for c in clips for a, b in c.record.windows() if b - a >= 3]
    if not windows:
        raise AgentFailure("assets", f"no {game} clip has a usable gameplay window of 3s or more")
    pieces: list[tuple[Path, float, float, str]] = []
    need = total_s + XFADE_S
    i = 0
    used: list[tuple[str, float]] = []
    while need > 0.05:
        # weight windows by length so long stretches are visited more, then pick a fresh spot in it
        c, a, b = rng.choices(windows, weights=[w[2] - w[1] for w in windows])[0]
        span = b - a - 0.05
        # cut to a different stretch every few seconds to keep the background lively
        length = min(need + XFADE_S, span, rng.uniform(MIN_CUT_S, MAX_CUT_S))
        length = max(length, min(span, 0.8))  # every piece must be longer than the crossfade
        start = a + rng.uniform(0, max(0.0, span - length))
        i += 1
        if any(cid == c.record.asset_id and abs(s - start) < MAX_CUT_S for cid, s in used) and i < 200:
            continue  # avoid showing the same stretch twice in one video when possible
        used.append((c.record.asset_id, start))
        pieces.append((c.record.path, round(start, 3), round(length, 3), c.record.asset_id))
        need -= length - XFADE_S
        if len(pieces) > 120:
            raise AgentFailure("assets", "gameplay clips are too short to fill the video")
    key = _h([(str(p), s, l) for p, s, l, _ in pieces], total_s, width, height, fps,
             [c.record.sha256 for c in clips])
    out = ctx.job.assets_dir / f"background_{key}.mp4"
    if out.exists():
        try:
            if abs(probe(out).duration - total_s) < 0.2:
                ctx.job.log.log("assets", "ffmpeg", "cached", output=out.name)
                return out, sorted({a for *_, a in pieces})
        except MediaError:
            pass
    cmd = [require_tool("ffmpeg"), "-v", "error", "-y"]
    for p, s, l, _ in pieces:
        cmd += ["-ss", f"{s}", "-t", f"{l}", "-i", str(p)]
    norm = (f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,"
            f"fps={fps},format=yuv420p")
    fl = [f"[{k}:v]{norm},settb=AVTB[v{k}]" for k in range(len(pieces))]
    last, offset = "v0", 0.0
    for k in range(1, len(pieces)):
        offset += pieces[k - 1][2] - XFADE_S
        fl.append(f"[{last}][v{k}]xfade=transition=fade:duration={XFADE_S}:offset={offset:.3f}[x{k}]")
        last = f"x{k}"
    cmd += ["-filter_complex", ";".join(fl), "-map", f"[{last}]", "-t", f"{total_s:.3f}", "-an"]
    cp = run([*cmd, *gpu.h264_args(20, "veryfast"), "-pix_fmt", "yuv420p", str(out)], timeout=1200)
    if cp.returncode != 0 and gpu.enabled():  # NVENC failed: the CPU encoder always works
        ctx.job.log.log("assets", "ffmpeg", "retry", reason="NVENC encode failed; retrying with libx264",
                        log_tail=cp.stderr[-600:])
        cp = run([*cmd, *gpu.h264_args(20, "veryfast", gpu=False), "-pix_fmt", "yuv420p", str(out)], timeout=1200)
    if cp.returncode != 0 or not out.exists():
        raise AgentFailure("assets", f"ffmpeg could not prepare gameplay background: {cp.stderr[-600:]}")
    info = probe(out)
    if not info.has_video or abs(info.duration - total_s) > 0.2:
        raise AgentFailure("assets", f"prepared background has wrong duration {info.duration:.2f}s")
    ctx.job.log.log("assets", "ffmpeg", "ok", tool_detail="gameplay background", output=out.name,
                    pieces=[{"asset_id": a, "start": s, "length": l} for _, s, l, a in pieces],
                    sha256=sha256(out), duration_s=info.duration)
    return out, sorted({a for *_, a in pieces})


# ---------------- music ----------------
def prepare_music(ctx: AgentContext) -> Path | None:
    """Only user-supplied music or manifest entries of type 'music' that are not rejected."""
    src = ctx.brief.music
    if src:
        p = Path(src)
        if not p.is_file():
            raise AgentFailure("assets", f"music file not found: {p.name}")
        try:
            if not probe(p).has_audio:
                raise AgentFailure("assets", "music file has no audio stream")
        except MediaError as e:
            raise AgentFailure("assets", f"music file is not readable: {e}") from e
        ctx.job.log.log("assets", "music", "ok", source="user supplied", file=p.name)
        return p
    return None


# ---------------- manim ----------------
def render_manim(ctx: AgentContext, storyboard: Storyboard, scene_durations: dict[str, float],
                 size: tuple[int, int], quality: str, palette: dict | None = None) -> dict[str, str]:
    clips: dict[str, str] = {}
    # a different card/title look for each Manim scene, starting from a per-video offset
    looks = list(manim_runner.LOOKS)
    first = ctx.rng.randrange(len(looks))
    n_manim = 0
    todo: list[tuple[str, dict, str]] = []
    for sc in storyboard.scenes:
        if sc.visual_type != "manim" or not sc.manim_template:
            continue
        params = {**sc.manim_template, "duration_s": max(2.0, min(20.0, scene_durations.get(sc.scene_id, 6) - 0.3))}
        params.setdefault("look", looks[(first + n_manim) % len(looks)])
        n_manim += 1
        if palette:
            params["palette"] = palette
        key = _h(params, size, quality, "transparent-webm")
        name = f"{sc.scene_id}_{key}"
        existing = ctx.job.assets_dir / "manim" / f"{name}.webm"
        if existing.exists():
            clips[sc.scene_id] = str(existing.relative_to(ctx.job.dir))
            ctx.job.log.log("manim", "manim", "cached", scene=sc.scene_id)
            continue
        todo.append((sc.scene_id, params, name))

    def one(item):
        _, params, name = item
        return manim_runner.render(params, ctx.job.assets_dir / "manim", name, quality=quality, size=size,
                                   transparent=True)

    # Each clip is its own single-threaded Manim process, so clips render side by side (2 clips: ~24 s -> ~13 s).
    with ThreadPoolExecutor(max(1, min(len(todo), MANIM_WORKERS))) as pool:
        results = list(pool.map(one, todo))
    for (scene_id, params, _), res in zip(todo, results):
        ctx.job.log.log("manim", "manim", "ok" if res.ok else "error", scene=scene_id,
                        template=params.get("template"), latency_s=round(res.elapsed_s, 2), error=res.error,
                        output=res.clip_path, sha256=res.sha256, returncode=res.returncode,
                        log_tail=res.log_tail[-600:] if not res.ok else "")
        if res.ok and res.clip_path:
            clips[scene_id] = str(Path(res.clip_path).relative_to(ctx.job.dir))
        else:
            ctx.notes.append(f"Manim failed for {scene_id} ({res.error}); a Remotion diagram is used instead")
    return clips


def build_manifest(ctx: AgentContext, segs: list[SegmentAudio], narration: Path | None, background: Path | None,
                   clip_ids: list[str], music: Path | None, manim: dict[str, str]) -> AssetManifest:
    job = ctx.job
    entries: list[AssetEntry] = []

    def add(asset_id, kind, path: Path, **kw):
        exists = path.is_file()
        info = None
        if exists:
            try:
                info = probe(path)
            except MediaError:
                exists = False
        entries.append(AssetEntry(asset_id=asset_id, kind=kind, path=str(path), exists=exists,
                                  sha256=sha256(path) if exists else None,
                                  duration_s=info.duration if info else None, width=info.width if info else None,
                                  height=info.height if info else None, **kw))

    for s in segs:
        add(s.segment_id, "narration_segment", job.dir / s.path, source=s.provider)
    if narration:
        add("narration", "narration", narration, source=segs[0].provider if segs else "")
    lib = {r.asset_id: r for r in gameplay.read_manifest()}
    for cid in clip_ids:
        r = lib.get(cid)
        if r:
            add(cid, "gameplay", r.path, source=r.source_page or r.source_url, license=r.license,
                review_status=r.review_status, notes=r.attribution_text)
    if background:
        add("background", "background_video", background, notes="derived from gameplay clips " + ", ".join(clip_ids))
    if music:
        add("music", "music", music, source="user supplied")
    for scene_id, rel in manim.items():
        add(f"manim_{scene_id}", "manim_clip", job.dir / rel, source="trusted Manim template")
    missing = [e.asset_id for e in entries if not e.exists]
    return AssetManifest(assets=entries, segments=segs, narration_path=str(narration) if narration else None,
                         narration_provider=segs[0].provider if segs else None, gameplay_clip_ids=clip_ids,
                         background_path=str(background) if background else None,
                         music_path=str(music) if music else None, manim_clips=manim, missing=missing)
