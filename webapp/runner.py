"""Starting work: new videos, new versions of a video, and resuming a stopped one.

The pipeline runs in a background thread; the job's state.json is the only progress source."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from webapp.config import AUDIO_EXT, EXEC_MODES, GPU_MODES, SOURCE_EXT, read_json, settings

# job id -> thread, for jobs this server process is running right now
running: dict[str, threading.Thread] = {}


def friendly_errors(err) -> list[str]:
    from pydantic import ValidationError
    names = {"topic": "Prompt", "audience": "Audience", "tone": "Tone", "duration_s": "Length", "cta": "Ending line",
             "must_include": "Must mention", "must_avoid": "Avoid", "voice": "Voice", "language": "Language"}
    if not isinstance(err, ValidationError):
        return [str(err)]
    out = []
    for e in err.errors():
        field = names.get(str(e["loc"][0]) if e["loc"] else "", "Form")
        kind, ctx, msg = e["type"], e.get("ctx") or {}, str(e.get("msg", ""))
        if "duration_s must be between" in msg:
            out.append("Length: full videos are 30 to 60 seconds. Turn on quick test for shorter ones.")
        elif field == "Prompt" and kind in ("string_too_short", "missing"):
            out.append("Write a few words about what the video should explain.")
        elif kind == "string_too_short":
            out.append(f"{field}: enter at least {ctx.get('min_length', 2)} characters.")
        elif kind == "string_too_long":
            out.append(f"{field}: shorten this to {ctx.get('max_length')} characters or fewer.")
        else:
            out.append(f"{field}: {msg.removeprefix('Value error, ')}")
    return out


def _or(value, default: str, min_len: int = 2) -> str:
    value = (value or "").strip() if isinstance(value, str) else ""
    return value if len(value) >= min_len else default


def _lines(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value or "").splitlines() if x.strip()]


def _upload_ok(path: str, allowed: set[str]) -> str:
    """Only files this server saved under outputs/_uploads may be used as sources."""
    if not path:
        return ""
    root = (settings().outputs_dir / "_uploads").resolve()
    p = Path(path).resolve()
    if root not in p.parents or not p.exists() or p.suffix.lower() not in allowed:
        raise ValueError(f"Attachment not found: {Path(path).name}")
    return str(p)


def start(fn) -> str:
    """Run fn(holder) in a thread and return the job id it puts in holder once the job folder exists."""
    holder: dict = {}

    def target():
        try:
            fn(holder)
        except Exception as e:  # noqa: BLE001 - the job's state.json records the failure
            holder["error"] = f"{type(e).__name__}: {e}"
        finally:
            if holder.get("job_id"):
                running.pop(holder["job_id"], None)

    th = threading.Thread(target=target, daemon=True)
    th.start()
    for _ in range(200):
        if "job_id" in holder or "error" in holder or not th.is_alive():
            break
        time.sleep(0.05)
    if "job_id" in holder:
        running[holder["job_id"]] = th
        return holder["job_id"]
    raise RuntimeError(holder.get("error") or "The job did not start.")


def new_job(data: dict) -> str:
    from schemas.brief import Brief
    dev = bool(data.get("quick_test"))
    brief = Brief.model_validate({
        "topic": (data.get("topic") or "").strip(),
        "audience": _or(data.get("audience"), "General audience"),
        "tone": _or(data.get("tone"), "engaging, clear"),
        "content_type": data.get("content_type") or "factual_explainer",
        "mode": data.get("mode") or "og",
        "duration_s": float(data.get("duration_s") or (12 if dev else 45)),
        "format": data.get("format") or "video_9x16",
        "language": _or(data.get("language"), "English"),
        "subtitle_language": _or(data.get("subtitle_language"), _or(data.get("language"), "English")),
        "must_include": _lines(data.get("must_include")),
        "must_avoid": _lines(data.get("must_avoid")),
        "cta": (data.get("cta") or "").strip(),
        "source_files": [_upload_ok(p, SOURCE_EXT) for p in data.get("source_files") or []],
        "source_text": data.get("source_text") or "",
        "narration_audio": _upload_ok(data.get("narration_audio") or "", AUDIO_EXT),
        "music": _upload_ok(data.get("music") or "", AUDIO_EXT),
        "dev_short": dev,
        "voice": data.get("voice") or "",
        "tts_engine": data.get("tts_engine") if data.get("tts_engine") in ("chatterbox", "edge") else "",
        "speed": int(data["speed"]) if str(data.get("speed", "")).lstrip("+-").isdigit() else None,
        "motion": data.get("motion") or "auto",
    })
    exec_mode = data.get("exec_mode") if data.get("exec_mode") in EXEC_MODES else None
    seed = int(data.get("seed") or 42)
    wiki = data.get("online_research")
    return _run(brief, exec_mode, seed, reuse=not data.get("fresh_script"),
                online=wiki if isinstance(wiki, bool) else None, gpu=data.get("gpu"))


def _saved_online(state: dict) -> bool | None:
    """The Wikipedia setting a job was made with, so its versions and resumes research the same way."""
    v = (state.get("config") or {}).get("online_research")
    return v if isinstance(v, bool) else None


def _saved_gpu(state: dict) -> str | None:
    """The GPU setting a job was made with (auto, on or off), reused by its versions and resumes."""
    v = (state.get("config") or {}).get("gpu")
    return v if v in GPU_MODES else None


def _run(brief, exec_mode, seed: int, reuse: bool, online: bool | None = None, gpu: str | None = None) -> str:
    def fn(holder):
        from orchestrator import Pipeline
        s = settings()
        if exec_mode:
            s.execution_mode = exec_mode
        if online is not None:
            s.online_research = online
        if gpu in GPU_MODES:
            s.gpu = gpu
        p = Pipeline(brief, settings=s, seed=seed, reuse_content=reuse)
        holder["job_id"] = p.job.id
        p.run()
    return start(fn)


def new_version(d: Path, data: dict) -> str:
    from schemas.brief import Brief
    base = Brief.model_validate(read_json(d / "brief.json"))
    state = read_json(d / "state.json") or {}
    update = {}
    if data.get("mode") in ("og", "minecraft", "subway"):
        update["mode"] = data["mode"]
    if "voice" in data:
        update["voice"] = data.get("voice") or ""
    if data.get("tts_engine") in ("chatterbox", "edge"):
        update["tts_engine"] = data["tts_engine"]
    # keep the original's AI setting so a local-only video does not start calling the API for its versions
    mode = (state.get("config") or {}).get("execution_mode")
    return _run(base.model_copy(update=update), mode if mode in EXEC_MODES else None, int(state.get("seed", 42)),
                reuse=True, online=_saved_online(state), gpu=_saved_gpu(state))


def resume(d: Path) -> str:
    """Run a failed or interrupted job again; finished stages are reused from its folder."""
    if d.name in running:
        return d.name
    state = read_json(d / "state.json") or {}

    def fn(holder):
        from orchestrator import Pipeline
        s = settings()
        if _saved_online(state) is not None:
            s.online_research = _saved_online(state)
        if _saved_gpu(state):
            s.gpu = _saved_gpu(state)
        p = Pipeline(job_id=d.name, settings=s, seed=int(state.get("seed", 42)))
        holder["job_id"] = p.job.id
        p.run()
    return start(fn)
