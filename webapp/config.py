"""Paths, limits and the helpers every other module uses to find and read job folders."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATIC = ROOT / "webui"
UI_ASSETS = ROOT / "assets" / "ui"
SOURCE_EXT = {".pdf", ".docx", ".txt", ".md"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
MAX_UPLOAD = 50_000_000
EXEC_MODES = {"AI_PREFERRED", "LOCAL_ONLY", "AI_REQUIRED"}
GPU_MODES = {"auto", "on", "off"}
# extra public hostnames (comma-separated) whose https pages may post to the app, e.g. a named tunnel
ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get("AGENTREEL_ALLOWED_HOSTS", "").split(",") if h.strip()}
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")


def settings():
    from core.config import Settings
    return Settings.from_env()


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def job_dir(job_id: str) -> Path | None:
    """The folder of an existing job, or None for unknown ids and anything outside outputs/."""
    if not ID_RE.match(job_id or ""):
        return None
    root = settings().outputs_dir.resolve()
    d = (root / job_id).resolve()
    if d.parent != root or not (d / "state.json").exists():
        return None
    return d
