"""Cross-job reuse of plan, research, script and storyboard.

A new version of the same video (another mode, voice, palette or caption style) should not pay for
planning, research and scripting again. Content is keyed by the brief fields that shape the words
plus the SHA-256 of every source file, so a different topic, PDF or duration never reuses anything.
Storyboards are also keyed by mode (OG scenes differ from gameplay scenes) and by the script they
were built from.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rendering.media_utils import sha256

CONTENT_FIELDS = ("topic", "audience", "tone", "language", "content_type", "duration_s", "must_include",
                  "must_avoid", "cta", "source_text", "dev_short")


def content_key(brief) -> str:
    data = {k: getattr(brief, k) for k in CONTENT_FIELDS}
    data["sources"] = sorted(sha256(f) for f in brief.source_files if Path(f).is_file())
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:20]


class ContentCache:
    def __init__(self, root: Path, key: str):
        self.dir = Path(root) / ".content_cache" / key
        self.key = key

    def _p(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def get(self, name: str) -> dict | None:
        p = self._p(name)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, name: str, data: dict, job_id: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._p(name).with_suffix(".tmp")
        tmp.write_text(json.dumps({"job_id": job_id, "data": data}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._p(name))
