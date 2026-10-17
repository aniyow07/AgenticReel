"""Gameplay asset library: manifest.csv, validation and clip selection.

The manifest is the single record of provenance. A clip is *usable* only when
the file exists, ffprobe finds a video stream, ffmpeg can decode it, its
checksum matches the manifest and its review status is not "rejected".
"""
from __future__ import annotations

import csv
import random
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from rendering.media_utils import MediaError, can_decode, probe, sha256

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.csv"
GAMES = {"minecraft": ASSETS / "gameplay" / "minecraft", "subway": ASSETS / "gameplay" / "subway"}
REVIEW_STATUSES = ("verified", "needs_review", "rejected")

FIELDS = ["asset_id", "relative_path", "type", "game", "source_url", "source_page", "creator", "license",
          "permission_evidence_url", "attribution_required", "attribution_text", "retrieval_date", "sha256",
          "duration_s", "width", "height", "fps", "video_codec", "usable_ranges", "review_status", "notes"]


@dataclass
class AssetRecord:
    asset_id: str
    relative_path: str
    type: str = "gameplay"
    game: str = ""
    source_url: str = ""
    source_page: str = ""
    creator: str = ""
    license: str = ""
    permission_evidence_url: str = ""
    attribution_required: str = "false"
    attribution_text: str = ""
    retrieval_date: str = ""
    sha256: str = ""
    duration_s: str = ""
    width: str = ""
    height: str = ""
    fps: str = ""
    video_codec: str = ""
    # "start-end;start-end" seconds of pure gameplay (skips intros, menus, outros). Empty = whole clip.
    usable_ranges: str = ""
    review_status: str = "needs_review"
    notes: str = ""

    @property
    def path(self) -> Path:
        p = Path(self.relative_path)
        return p if p.is_absolute() else ROOT / p

    def windows(self) -> list[tuple[float, float]]:
        dur = float(self.duration_s or 0)
        if not self.usable_ranges.strip():
            return [(0.0, dur)] if dur else []
        out = []
        for part in self.usable_ranges.split(";"):
            try:
                a, b = (float(x) for x in part.split("-"))
            except ValueError:
                continue
            a, b = max(0.0, a), min(b, dur) if dur else b
            if b - a >= 1.0:
                out.append((a, b))
        return out


@dataclass
class ClipStatus:
    record: AssetRecord
    exists: bool
    usable: bool
    problems: list[str] = field(default_factory=list)
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None

    def as_row(self) -> dict:
        r = self.record
        return {"asset": r.asset_id, "game": r.game, "file": r.relative_path, "exists": self.exists,
                "usable": self.usable, "duration_s": self.duration_s, "resolution":
                f"{self.width}x{self.height}" if self.width else "", "review_status": r.review_status,
                "license": r.license, "problems": "; ".join(self.problems)}


def read_manifest(path: Path | None = None) -> list[AssetRecord]:
    path = path or MANIFEST
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        out.append(AssetRecord(**{k: row.get(k, "") or "" for k in FIELDS}))
    return out


def write_manifest(records: list[AssetRecord], path: Path | None = None) -> None:
    path = path or MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in records:
            w.writerow(asdict(r))
    tmp.replace(path)


def upsert(record: AssetRecord, path: Path | None = None) -> None:
    recs = [r for r in read_manifest(path) if r.asset_id != record.asset_id]
    recs.append(record)
    write_manifest(recs, path)


def fill_media_fields(record: AssetRecord) -> AssetRecord:
    info = probe(record.path)
    record.sha256 = sha256(record.path)
    record.duration_s = f"{info.duration:.3f}"
    record.width, record.height = str(info.width or ""), str(info.height or "")
    record.fps = f"{info.fps:.3f}" if info.fps else ""
    record.video_codec = info.video_codec or ""
    record.retrieval_date = record.retrieval_date or date.today().isoformat()
    return record


def check_clip(record: AssetRecord, deep: bool = True) -> ClipStatus:
    st = ClipStatus(record=record, exists=record.path.is_file(), usable=False)
    if record.review_status not in REVIEW_STATUSES:
        st.problems.append(f"unknown review status {record.review_status!r}")
    if record.review_status == "rejected":
        st.problems.append("review status is rejected")
    if not st.exists:
        st.problems.append("file is missing")
        return st
    try:
        info = probe(record.path)
    except MediaError as e:
        st.problems.append(str(e))
        return st
    st.duration_s, st.width, st.height = round(info.duration, 2), info.width, info.height
    if not info.has_video:
        st.problems.append("no video stream")
    if info.duration < 3:
        st.problems.append("clip shorter than 3 seconds")
    if deep:
        ok, err = can_decode(record.path)
        if not ok:
            st.problems.append(f"ffmpeg could not decode the clip: {err}")
        if record.sha256 and sha256(record.path) != record.sha256:
            st.problems.append("checksum differs from the manifest (file changed since it was recorded)")
    st.usable = not st.problems
    return st


def library_status(deep: bool = False) -> dict[str, list[ClipStatus]]:
    recs = read_manifest()
    out: dict[str, list[ClipStatus]] = {g: [] for g in GAMES}
    for r in recs:
        if r.type == "gameplay" and r.game in out:
            out[r.game].append(check_clip(r, deep=deep))
    return out


class GameplayUnavailable(RuntimeError):
    pass


def usable_clips(game: str, deep: bool = True) -> list[ClipStatus]:
    if game not in GAMES:
        raise ValueError(f"unknown game {game!r}")
    return [c for c in library_status(deep=False)[game] if (check_clip(c.record, deep=deep).usable)]


def select_clips(game: str, needed_s: float, seed: int | None = None) -> list[ClipStatus]:
    """Pick clips (deterministically for a seed) until there is enough footage; clips may repeat."""
    clips = usable_clips(game, deep=True)
    if not clips:
        raise GameplayUnavailable(
            f"No usable {game} gameplay clip is available. Run `python scripts/setup_gameplay_assets.py "
            f"--game {game}` or register your own recording with --register. AgentReel will not substitute "
            f"other footage.")
    rng = random.Random(seed)
    order = clips[:]
    rng.shuffle(order)
    return order


