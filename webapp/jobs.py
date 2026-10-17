"""Read-only views of job folders: library rows, the detail page, live progress and poster frames."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from webapp.config import job_dir, read_json, settings
from webapp.runner import running

# The pipeline's stages in the order it actually runs them (core.jobs.STAGES lists assets before tts),
# with the short names and "now doing" lines the UI shows.
ORDER = ["planning", "research", "scripting", "storyboarding", "tts", "assets", "manim", "editing",
         "remotion_render", "ffmpeg", "qa"]
STEP_NAMES = {
    "planning": "Plan", "research": "Research", "scripting": "Script", "storyboarding": "Storyboard",
    "assets": "Visuals", "tts": "Voice", "manim": "Animation", "editing": "Edit",
    "remotion_render": "Render", "ffmpeg": "Mix", "qa": "Check",
}
STEP_NOW = {
    "planning": "Planning the video", "research": "Reading your sources", "scripting": "Writing the script",
    "storyboarding": "Planning each scene", "assets": "Preparing visuals and footage", "tts": "Recording the voice",
    "manim": "Animating diagrams", "editing": "Putting the timeline together", "remotion_render": "Rendering video",
    "ffmpeg": "Mixing audio", "qa": "Checking the result",
}
WRITING_STAGES = ("planning", "research", "scripting", "storyboarding")


def poster(d: Path) -> Path | None:
    """One cached poster frame per video, taken a third of the way in (the first frames are often a title card)."""
    out = d / "render" / "poster_web.jpg"
    final = d / "final.mp4"
    if out.exists() or not final.exists():
        return out if out.exists() else None
    from rendering.media_utils import tool_path
    ff, fp = tool_path("ffmpeg"), tool_path("ffprobe")
    if not ff:
        return None
    at = 2.0
    if fp:
        try:
            dur = float(subprocess.run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(final)], capture_output=True, text=True, timeout=30).stdout.strip())
            at = max(0.5, dur * 0.33)
        except (ValueError, subprocess.SubprocessError):
            pass
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(final), "-vf", "scale=540:-2",
                    "-frames:v", "1", "-q:v", "3", str(out)], capture_output=True, timeout=60)
    return out if out.exists() else None


def step_sources(d: Path) -> tuple[dict, str]:
    """Which writing steps used the AI, were reused from an earlier video, or fell back to templates
    (read from the job's run log), plus the reason the AI was skipped, if any."""
    out, why = {}, ""
    p = d / "logs" / "run_log.jsonl"
    if not p.exists():
        return out, why
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out, why
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        st = r.get("stage")
        if st not in WRITING_STAGES:
            continue
        if r.get("status") == "reused":
            out[st] = "reused"
        elif r.get("origin") in ("llm", "local") and out.get(st) != "reused":
            out[st] = "ai" if r["origin"] == "llm" else "template"
        if r.get("status") in ("fallback_to_local", "unavailable") and not why:
            why = r.get("error") or r.get("reason") or ""
    low = why.lower()
    if ("daily" in low and "limit" in low) or "quota" in low:
        why = "the AI provider's free daily limit is used up"
    elif "no api key" in low:
        why = "no API key is set for the AI provider"
    elif why:
        why = "the AI provider did not answer"
    return out, why


def progress(state: dict, d: Path | None = None) -> dict:
    stages = state.get("stages", {})
    cur = state.get("current_stage")
    steps, done = [], 0
    for k in ORDER:
        stt = stages.get(k, {}).get("status", "pending")
        if stt in ("done", "skipped"):
            done += 1
        steps.append({"key": k, "name": STEP_NAMES.get(k, k), "status": stt, "current": k == cur,
                      "attempts": stages.get(k, {}).get("attempts", 0)})
    srcs, why = step_sources(d) if d is not None else ({}, "")
    for s in steps:
        s["source"] = srcs.get(s["key"], "")
    frac, now = 0.0, STEP_NOW.get(cur, "Starting")
    if cur == "remotion_render" and d is not None:
        rp = read_json(d / "render" / "render_progress.json")  # written by remotion_runner while it renders
        if rp and rp.get("total"):
            frac = min(1.0, rp["rendered"] / rp["total"])
            now = f"Rendering frame {rp['rendered']} of {rp['total']}"
    return {"pct": int(100 * (done + frac) / len(ORDER)), "now": now, "steps": steps, "ai_skipped": why}


def _recent(state: dict) -> bool:
    """A job another process is running still updates state.json; one that stopped long ago was interrupted."""
    from datetime import datetime, timezone
    try:
        ts = datetime.fromisoformat(state.get("updated_at") or state.get("created_at"))
        return (datetime.now(timezone.utc) - ts).total_seconds() < 15 * 60
    except (TypeError, ValueError):
        return False


def _group_key(brief: dict, state: dict) -> str:
    """Versions of a video share their prompt and attached documents."""
    topic = " ".join((brief.get("topic") or state.get("topic") or "").lower().split())
    files = ",".join(sorted(Path(f).name.split("_", 1)[-1] for f in brief.get("source_files") or []))
    return f"{topic}|{files}"


def summary(d: Path, state: dict | None = None) -> dict:
    state = state or read_json(d / "state.json") or {}
    brief = read_json(d / "brief.json") or {}
    script = read_json(d / "script.json") or {}
    qa = read_json(d / "qa_report.json") or {}
    status = state.get("status") or "created"
    is_running = status in ("created", "running") and (d.name in running or _recent(state))
    out = {
        "id": d.name,
        "title": (read_json(d / "meta.json") or {}).get("title") or script.get("title") or brief.get("topic")
        or state.get("topic") or d.name,
        "topic": brief.get("topic") or state.get("topic") or "",
        "mode": state.get("mode") or brief.get("mode") or "og",
        "status": "running" if is_running else ("interrupted" if status in ("created", "running") else status),
        "created_at": state.get("created_at"),
        "duration_s": (qa.get("output") or {}).get("duration_s") or brief.get("duration_s"),
        "is_test": bool(state.get("is_test_render")),
        "has_video": (d / "final.mp4").exists(),
        "voice": brief.get("voice") or "",
        "group": _group_key(brief, state),
    }
    if is_running:
        out["progress"] = progress(state, d)
    return out


SCENE_KINDS = {
    "title": "Title", "text_reveal": "Text", "key_points": "Key points", "comparison": "Comparison", "stat": "Number",
    "quote": "Quote", "end_card": "Ending", "gameplay": "Gameplay", "process": "Steps",
    "process_diagram": "Process diagram", "flow_diagram": "Flow diagram", "timeline": "Timeline",
    "simple_chart": "Chart", "equation_steps": "Equation", "chemical_reaction": "Reaction",
    "array_algorithm": "Algorithm", "agent_loop": "Agent loop", "security_flow": "Security",
}


def scenes_preview(d: Path) -> list[dict]:
    """The storyboard's scenes as short cards for the live preview on the Rendering screen."""
    sb = read_json(d / "storyboard.json") or {}
    out = []
    for sc in sb.get("scenes", [])[:12]:
        mt = sc.get("manim_template") or {}
        vp = sc.get("visual_parameters") or {}
        kind = SCENE_KINDS.get(mt.get("template") or sc.get("visual_type"), (sc.get("visual_type") or "").replace("_", " "))
        items = (mt.get("steps") or mt.get("inputs") or [e.get("label", "") for e in mt.get("events") or []]
                 or mt.get("lines") or mt.get("reactants") or [str(v) for v in mt.get("values") or []]
                 or [x for x in (mt.get("attack"), mt.get("defense"), mt.get("target")) if x]
                 or mt.get("labels") or [s.get("text", "") if isinstance(s, dict) else s for s in mt.get("lines") or []]
                 or vp.get("points") or vp.get("items") or [])
        text = sc.get("on_screen_text") or mt.get("title") or vp.get("title") or vp.get("heading") or vp.get("text") or ""
        out.append({"kind": kind.capitalize() if kind and kind[0].islower() else kind, "text": str(text)[:90],
                    "items": [str(x)[:40] for x in items if x][:5]})
    return out


def detail(d: Path) -> dict:
    state = read_json(d / "state.json") or {}
    out = summary(d, state)
    out["progress"] = progress(state, d)
    brief = read_json(d / "brief.json") or {}
    out["brief"] = {k: brief.get(k) for k in ("topic", "audience", "tone", "content_type", "language",
                                               "subtitle_language", "format", "voice", "motion", "duration_s")}
    out["sources"] = [Path(f).name for f in brief.get("source_files") or []]
    script = read_json(d / "script.json") or {}
    out["script"] = [s.get("text", "") for s in script.get("segments", [])]
    out["script_origin"] = script.get("origin")
    out["scenes"] = scenes_preview(d)
    qa = read_json(d / "qa_report.json")
    if qa:
        checks = qa.get("checks", [])
        out["qa"] = {"passed": qa.get("technical_pass"), "total": len(checks),
                     "ok": sum(1 for c in checks if c.get("passed")),
                     "review": qa.get("semantic_status"),
                     "failed": [{"name": c["name"].replace("_", " "), "detail": c.get("detail", ""),
                                 "severity": c.get("severity")} for c in checks if not c.get("passed")]}
    facts = read_json(d / "facts.json") or {}
    out["facts"] = [{"claim": f.get("claim"), "status": f.get("status"), "source": f.get("source"),
                     "page": f.get("page")} for f in facts.get("facts", [])][:60]
    out["notes"] = state.get("notes") or []
    errs = state.get("errors") or []
    out["error"] = state.get("error") or (errs[-1]["error"] if errs and out["status"] == "failed" else "")
    final = d / "final.mp4"
    out["size_mb"] = round(final.stat().st_size / 1e6, 1) if final.exists() else None
    out["llm_calls"] = state.get("llm_calls", 0)
    out["provider"] = {"gemini": "Gemini", "openrouter": "OpenRouter"}.get(state.get("llm_provider") or "", "")
    return out


def list_all() -> list[dict]:
    from core.jobs import list_jobs
    rows = []
    for st in list_jobs(settings().outputs_dir):
        jid = st.get("job_id")
        d = job_dir(jid) if jid else None
        if d:
            rows.append(summary(d, st))
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r["id"])
    for r in rows:
        r["versions"] = len(groups[r["group"]])
    return rows


def warm_posters() -> None:
    """Make every missing poster up front so the library shows thumbnails at once."""
    for r in list_all():
        d = job_dir(r["id"])
        if d and r["has_video"]:
            try:
                poster(d)
            except Exception:  # noqa: BLE001 - a missing poster only means a blank tile
                pass
