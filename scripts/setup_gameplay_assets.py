"""Download, validate and register real gameplay footage.

    python scripts/setup_gameplay_assets.py                    # all configured sources
    python scripts/setup_gameplay_assets.py --game minecraft   # one game
    python scripts/setup_gameplay_assets.py --status           # show what is ready
    python scripts/setup_gameplay_assets.py --game subway --url https://... --creator "..." --license "..."
    python scripts/setup_gameplay_assets.py --game minecraft --register my_clip.mp4 --creator me --license "own recording"

Only URLs from assets/gameplay_sources.yaml or ones you pass explicitly are downloaded.
Downloads resume after interruption (HTTP Range) and valid files are never re-downloaded.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import yaml  # noqa: E402

from core.gameplay import GAMES, AssetRecord, check_clip, fill_media_fields, library_status, read_manifest, upsert  # noqa: E402
from core.jobs import safe_filename  # noqa: E402

SOURCES = ROOT / "assets" / "gameplay_sources.yaml"
UA = "AgentReel-setup/0.1 (local gameplay asset setup)"
MAX_BYTES = 2_000_000_000


def load_sources() -> list[dict]:
    data = yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}
    return data.get("sources", [])


def download(url: str, dest: Path, retries: int = 4) -> None:
    """Resumable download into dest.part, then atomically renamed."""
    if not url.lower().startswith("https://"):
        raise ValueError("only https:// URLs are downloaded")
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": UA}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as r:
                if r.status_code == 416:  # already complete
                    break
                if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
                    raise PermissionError(f"HTTP {r.status_code} from {r.url.host} (not retried)")
                if r.status_code not in (200, 206):
                    raise RuntimeError(f"HTTP {r.status_code} from {r.url.host}")
                if r.status_code == 200 and have:
                    have = 0  # server ignored Range; start again
                    part.unlink(missing_ok=True)
                total = int(r.headers.get("content-length") or 0) + have
                if total > MAX_BYTES:
                    raise RuntimeError(f"file is larger than the {MAX_BYTES // 1_000_000} MB limit")
                done, last = have, 0.0
                with open(part, "ab") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        if time.time() - last > 1:
                            pct = f"{done / total * 100:5.1f}%" if total else ""
                            print(f"\r  {done / 1e6:8.1f} MB {pct}", end="", flush=True)
                            last = time.time()
                print(f"\r  {done / 1e6:8.1f} MB done      ")
                if total and done < total:
                    raise RuntimeError("connection closed early")
            break
        except (httpx.HTTPError, RuntimeError) as e:
            if attempt == retries:
                raise RuntimeError(f"download failed after {retries} attempts: {e}") from e
            wait = 2 ** attempt
            print(f"\n  attempt {attempt} failed ({e}); retrying in {wait}s")
            time.sleep(wait)
    part.replace(dest)


def setup_source(src: dict, force: bool = False) -> bool:
    game = src["game"]
    dest = GAMES[game] / safe_filename(src["filename"])
    rel = dest.relative_to(ROOT).as_posix()
    print(f"[{game}] {src['asset_id']}")
    if src.get("review_status") == "rejected":
        print("  skipped: source is marked rejected")
        return False
    existing = {r.asset_id: r for r in read_manifest()}.get(src["asset_id"])
    if existing and dest.exists() and not force:
        st = check_clip(existing)
        if st.usable:
            print(f"  already present and valid ({st.duration_s}s {st.width}x{st.height}); not re-downloading")
            return True
        print(f"  existing file is not valid ({'; '.join(st.problems)}); downloading again")
        dest.unlink(missing_ok=True)
    print(f"  downloading from {src['url'][:90]}...")
    download(src["url"], dest)
    rec = AssetRecord(asset_id=src["asset_id"], relative_path=rel, type="gameplay", game=game,
                      source_url=src["url"], source_page=src.get("source_page", ""), creator=src.get("creator", ""),
                      license=src.get("license", ""), permission_evidence_url=src.get("permission_evidence_url", ""),
                      attribution_required=str(bool(src.get("attribution_required", False))).lower(),
                      attribution_text=src.get("attribution_text", ""), retrieval_date=date.today().isoformat(),
                      review_status=src.get("review_status", "needs_review"), notes=src.get("notes", "").strip(),
                      usable_ranges=src.get("usable_ranges", ""))
    return register_record(rec)


def register_record(rec: AssetRecord) -> bool:
    try:
        fill_media_fields(rec)
    except Exception as e:  # MediaError, OSError
        print(f"  INVALID: {e}")
        return False
    st = check_clip(rec)
    if not st.usable:
        print(f"  INVALID: {'; '.join(st.problems)}")
        rec.notes = (rec.notes + " | validation failed: " + "; ".join(st.problems)).strip(" |")
        upsert(rec)
        return False
    upsert(rec)
    print(f"  OK: {rec.duration_s}s {rec.width}x{rec.height} {rec.video_codec} sha256={rec.sha256[:12]}â€¦ "
          f"review_status={rec.review_status}")
    return True


def print_status() -> None:
    status = library_status(deep=True)
    for game, clips in status.items():
        print(f"{game}:")
        if not clips:
            print("  (no clips registered)")
        for c in clips:
            r = c.as_row()
            print(f"  {r['asset']}: usable={r['usable']} {r['duration_s']}s {r['resolution']} "
                  f"review={r['review_status']} {r['problems']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", choices=sorted(GAMES))
    ap.add_argument("--status", action="store_true", help="only report what is installed")
    ap.add_argument("--force", action="store_true", help="re-download even if a valid file exists")
    ap.add_argument("--url", help="direct https URL of an authorized clip (requires --game)")
    ap.add_argument("--register", help="register a clip you placed or recorded yourself (requires --game)")
    ap.add_argument("--asset-id")
    ap.add_argument("--creator", default="")
    ap.add_argument("--license", default="")
    ap.add_argument("--source-page", default="")
    ap.add_argument("--permission-url", default="")
    ap.add_argument("--attribution", default="")
    ap.add_argument("--usable-ranges", default="", help="e.g. 5-60;75-180 (seconds of pure gameplay)")
    ap.add_argument("--review-status", choices=["verified", "needs_review", "rejected"], default="needs_review")
    a = ap.parse_args()

    if a.status:
        print_status()
        return 0
    if a.url or a.register:
        if not a.game:
            ap.error("--game is required with --url/--register")
        if not a.license:
            ap.error("--license is required: describe the permission you have for this clip")
        asset_id = a.asset_id or f"{a.game}_{safe_filename(Path(a.url or a.register).stem)[:40]}"
        dest = GAMES[a.game] / f"{asset_id}.mp4"
        if a.url:
            download(a.url, dest)
        else:
            srcp = Path(a.register).resolve()
            if not srcp.is_file():
                ap.error(f"file not found: {srcp}")
            if srcp != dest.resolve():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(srcp, dest)
        rec = AssetRecord(asset_id=asset_id, relative_path=dest.relative_to(ROOT).as_posix(), game=a.game,
                          source_url=a.url or f"local file: {Path(a.register).name}", source_page=a.source_page,
                          creator=a.creator, license=a.license, permission_evidence_url=a.permission_url,
                          attribution_required=str(bool(a.attribution)).lower(), attribution_text=a.attribution,
                          review_status=a.review_status, usable_ranges=a.usable_ranges)
        return 0 if register_record(rec) else 1

    ok = True
    for src in load_sources():
        if a.game and src["game"] != a.game:
            continue
        try:
            ok = setup_source(src, force=a.force) and ok
        except Exception as e:
            print(f"  FAILED: {e}")
            ok = False
    print()
    print_status()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())



