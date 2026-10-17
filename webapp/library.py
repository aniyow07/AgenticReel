"""Renaming videos, and deleting them to outputs/_trash so they can be restored."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from webapp.config import ID_RE, job_dir, read_json, settings
from webapp.jobs import list_all, summary
from webapp.runner import running


def clean_name(text: str, limit: int = 100) -> str:
    """A file or display name: no characters Windows forbids in file names, no control characters."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text or "")
    return " ".join(text.split())[:limit].strip(" .")


def download_name(d: Path, wanted: str = "") -> str:
    return clean_name(wanted) or clean_name(summary(d)["title"]) or d.name


def rename(d: Path, title: str) -> str:
    """The title the app shows and downloads use; kept beside the job so the pipeline files stay untouched."""
    title = clean_name(title, 120)
    if len(title) < 1:
        raise ValueError("Enter a name for the video.")
    meta = read_json(d / "meta.json") or {}
    meta["title"] = title
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return title


def _move(src: Path, dst: Path) -> None:
    """Rename a folder; Windows refuses while a file in it is open (the video player), so retry briefly."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(20):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == 19:
                raise ValueError("A file in this video is still open. Pause or close the video and try again.")
            time.sleep(0.15)


def trash_dir() -> Path:
    return settings().outputs_dir / "_trash"


def delete(d: Path, all_versions: bool) -> list[str]:
    """Move a video (or every version of it) to outputs/_trash so it can be restored."""
    ids = [d.name]
    if all_versions:
        group = summary(d)["group"]
        ids = [r["id"] for r in list_all() if r["group"] == group]
    if any(i in running for i in ids):
        raise ValueError("A version is still rendering. Wait for it to finish, then delete it.")
    done = []
    for i in ids:
        src = job_dir(i)
        if src:
            _move(src, trash_dir() / i)
            done.append(i)
    return done


def restore(ids: list[str]) -> list[str]:
    root = settings().outputs_dir
    done = []
    for i in ids:
        if not ID_RE.match(i or ""):
            continue
        src = trash_dir() / i
        if src.is_dir() and not (root / i).exists():
            _move(src, root / i)
            done.append(i)
    return done
