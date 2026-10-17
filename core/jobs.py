"""Job directories, persisted state and per-stage caching.

Each job lives in outputs/<job_id>/ and keeps state.json with the brief,
configuration, stage statuses, input fingerprints, errors and final paths.
A stage is reused on resume only when it completed, its artifacts still exist
and the fingerprint of its inputs is unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from core.runlog import RunLogger, now_iso

STAGES = ["planning", "research", "scripting", "storyboarding", "assets", "tts", "manim", "editing",
          "remotion_render", "ffmpeg", "qa"]

STAGE_LABELS = {
    "planning": "Planning", "research": "Research", "scripting": "Scripting", "storyboarding": "Storyboarding",
    "assets": "Asset preparation", "manim": "Manim rendering", "tts": "TTS", "editing": "Editing / timeline",
    "remotion_render": "Remotion rendering", "ffmpeg": "FFmpeg processing", "qa": "QA",
}

_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")


def new_job_id(prefix: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prefix = re.sub(r"[^A-Za-z0-9_\-]", "", prefix)[:24]
    return f"{prefix + '-' if prefix else ''}{stamp}-{secrets.token_hex(3)}"


def safe_job_id(job_id: str) -> str:
    if not _ID_RE.match(job_id or ""):
        raise ValueError(f"invalid job id: {job_id!r}")
    return job_id


def safe_filename(name: str, default: str = "file") -> str:
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._\-]", "_", base).strip("._") or default
    return base[:120]


def fingerprint(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, BaseModel):
            p = p.model_dump(mode="json")
        h.update(json.dumps(p, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:16]


class Job:
    def __init__(self, root: Path, job_id: str):
        self.id = safe_job_id(job_id)
        self.dir = (Path(root) / self.id).resolve()
        if Path(root).resolve() not in self.dir.parents:
            raise ValueError("job directory escapes the outputs folder")
        self.assets_dir = self.dir / "assets"
        self.logs_dir = self.dir / "logs"
        self.public_dir = self.dir / "public"  # Remotion --public-dir for this job
        for d in (self.dir, self.assets_dir, self.assets_dir / "audio", self.assets_dir / "manim", self.logs_dir,
                  self.public_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        self._lock = threading.Lock()
        self.log = RunLogger(self.id, self.logs_dir)
        self.state = self._load()

    # ---- state ----
    def _load(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"job_id": self.id, "created_at": now_iso(), "status": "created", "current_stage": None,
                "stages": {s: {"status": "pending"} for s in STAGES}, "errors": [], "repairs": 0, "outputs": {}}

    def save(self) -> None:
        with self._lock:
            self.state["updated_at"] = now_iso()
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, indent=2, default=str), encoding="utf-8")
            # On Windows the rename fails while a reader (e.g. the UI) has state.json open; retry briefly.
            for attempt in range(40):
                try:
                    tmp.replace(self.state_path)
                    break
                except PermissionError:
                    if attempt == 39:
                        raise
                    time.sleep(0.025 * (attempt + 1))

    def set(self, **kv) -> None:
        self.state.update(kv)
        self.save()

    def stage_start(self, stage: str, detail: str = "") -> None:
        st = self.state["stages"].setdefault(stage, {})
        st.update(status="running", started_at=now_iso(), detail=detail)
        st["attempts"] = st.get("attempts", 0) + 1
        self.state["current_stage"] = stage
        self.state["status"] = "running"
        self.save()

    def stage_done(self, stage: str, status: str = "done", fp: str | None = None, artifacts: list[str] | None = None,
                   detail: str = "") -> None:
        st = self.state["stages"].setdefault(stage, {})
        st.update(status=status, finished_at=now_iso(), detail=detail)
        if fp is not None:
            st["fingerprint"] = fp
        if artifacts is not None:
            st["artifacts"] = artifacts
        self.save()

    def stage_fail(self, stage: str, error: str) -> None:
        st = self.state["stages"].setdefault(stage, {})
        st.update(status="failed", finished_at=now_iso(), error=error[:2000])
        self.state["errors"].append({"stage": stage, "error": error[:2000], "at": now_iso()})
        self.save()

    def invalidate_from(self, stage: str) -> None:
        """Mark a stage and everything after it as needing a rerun."""
        idx = STAGES.index(stage)
        for s in STAGES[idx:]:
            if self.state["stages"].get(s, {}).get("status") in ("done", "skipped", "failed"):
                self.state["stages"][s]["status"] = "stale"
        self.save()

    def cached(self, stage: str, fp: str) -> bool:
        st = self.state["stages"].get(stage, {})
        if st.get("status") not in ("done", "skipped") or st.get("fingerprint") != fp:
            return False
        return all((self.dir / a).exists() for a in st.get("artifacts", []))

    # ---- artifacts ----
    def path(self, rel: str) -> Path:
        p = (self.dir / rel).resolve()
        if self.dir not in p.parents and p != self.dir:
            raise ValueError(f"path escapes the job folder: {rel}")
        return p

    def write_json(self, rel: str, obj) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return p

    def read_json(self, rel: str, model: type[BaseModel] | None = None):
        data = json.loads(self.path(rel).read_text(encoding="utf-8"))
        return model.model_validate(data) if model else data

    def write_text(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def exists(self, rel: str) -> bool:
        return self.path(rel).exists()


def list_jobs(root: Path) -> list[dict]:
    out = []
    for d in sorted(Path(root).glob("*/state.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            s = json.loads(d.read_text(encoding="utf-8"))
            out.append(s)
        except (OSError, json.JSONDecodeError):
            continue
    return out

