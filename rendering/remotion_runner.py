"""Renders a validated timeline with the Remotion CLI.

Media is staged into the job's own public directory (hard links where
possible, so large gameplay files are not duplicated) and the CLI is pointed
at it with --public-dir. Compositions reference media with staticFile(), never
with absolute Windows paths. Props travel in a JSON file because inline JSON is
not supported on Windows shells.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from pydantic import BaseModel

from rendering.media_utils import MediaError, probe, sha256
from schemas.render_props import COMPOSITION_FOR_MODE, RenderProps

ROOT = Path(__file__).resolve().parent.parent
REMOTION_DIR = ROOT / "remotion"
ENTRY = "src/index.ts"


class RenderResult(BaseModel):
    ok: bool
    output: str | None = None
    composition: str
    returncode: int | None = None
    elapsed_s: float = 0
    error: str | None = None
    log_tail: str = ""
    probe: dict | None = None
    sha256: str | None = None
    command: list[str] = []


def cli_command() -> list[str]:
    node = shutil.which("node")
    cli = REMOTION_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not node:
        raise MediaError("Node.js was not found on PATH")
    if not cli.exists():
        raise MediaError("Remotion is not installed; run `npm install` in the remotion folder")
    return [node, str(cli)]


def is_available() -> bool:
    try:
        cli_command()
        return True
    except MediaError:
        return False


_PROGRESS_RE = re.compile(r"Rendered (\d+)/(\d+)")


def run_with_progress(cmd: list[str], timeout: float, cwd: Path, progress_path: Path | None) -> subprocess.CompletedProcess:
    """Like media_utils.run, but streams the CLI output so "Rendered n/total" lines can be written to
    progress_path while the render runs (the web UI shows them). Output is still returned in full."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    out: dict[str, list[str]] = {"stdout": [], "stderr": []}
    last = [0.0]

    def pump(stream, key):
        for line in stream:
            out[key].append(line)
            m = _PROGRESS_RE.search(line)
            if m and progress_path and time.time() - last[0] > 0.5:
                last[0] = time.time()
                try:
                    progress_path.write_text(json.dumps({"rendered": int(m.group(1)), "total": int(m.group(2))}),
                                             encoding="utf-8")
                except OSError:
                    pass

    threads = [threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True)]
    for t in threads:
        t.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    finally:
        for t in threads:
            t.join(timeout=5)
        if progress_path:
            progress_path.unlink(missing_ok=True)
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(out["stdout"]), "".join(out["stderr"]))


def check_staged_media(props: RenderProps, public_dir: Path) -> list[str]:
    """Every media path in the props must exist inside the public dir."""
    missing = []
    root = public_dir.resolve()
    for rel in props.media_paths():
        p = (root / rel).resolve()
        if root not in p.parents or not p.is_file():
            missing.append(rel)
    return missing


def render(props: RenderProps, public_dir: Path, props_path: Path, output: Path, *, concurrency: int | None = None,
           timeout: float = 3600, crf: int = 20, scale: float | None = None) -> RenderResult:
    comp = COMPOSITION_FOR_MODE[props.mode]
    t0 = time.time()
    props = RenderProps.model_validate(props.model_dump())  # re-validate after any edits
    missing = check_staged_media(props, public_dir)
    if missing:
        return RenderResult(ok=False, composition=comp, error=f"staged media missing: {missing}")
    props_path.write_text(props.model_dump_json(indent=2), encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    cmd = [*cli_command(), "render", ENTRY, comp, str(output.resolve()), f"--props={props_path.resolve()}",
           f"--public-dir={public_dir.resolve()}", "--codec=h264", "--pixel-format=yuv420p", f"--crf={crf}",
           "--audio-codec=aac", "--log=info", "--overwrite"]
    cmd.append(f"--concurrency={concurrency or max(1, min(6, (os.cpu_count() or 2) // 2))}")
    if scale:
        cmd.append(f"--scale={scale}")
    try:
        cp = run_with_progress(cmd, timeout, REMOTION_DIR, output.parent / "render_progress.json")
    except Exception as e:
        return RenderResult(ok=False, composition=comp, error=f"Remotion did not finish: {e}", command=cmd,
                            elapsed_s=time.time() - t0)
    tail = (cp.stdout[-2500:] + "\n" + cp.stderr[-2500:]).strip()
    if cp.returncode != 0:
        return RenderResult(ok=False, composition=comp, returncode=cp.returncode, log_tail=tail, command=cmd,
                            error="Remotion render failed", elapsed_s=time.time() - t0)
    if not output.exists():
        return RenderResult(ok=False, composition=comp, returncode=0, log_tail=tail, command=cmd,
                            error="Remotion exited cleanly but the output file does not exist",
                            elapsed_s=time.time() - t0)
    try:
        info = probe(output)
    except MediaError as e:
        return RenderResult(ok=False, composition=comp, returncode=0, log_tail=tail, command=cmd, error=str(e),
                            elapsed_s=time.time() - t0)
    expected = props.durationInFrames / props.fps
    if not info.has_video or abs(info.duration - expected) > max(0.5, 2 / props.fps):
        return RenderResult(ok=False, composition=comp, returncode=0, log_tail=tail, command=cmd,
                            probe=info.summary(), elapsed_s=time.time() - t0,
                            error=f"rendered duration {info.duration:.2f}s does not match expected {expected:.2f}s")
    return RenderResult(ok=True, output=str(output), composition=comp, returncode=0, log_tail=tail[-1200:],
                        probe=info.summary(), sha256=sha256(output), command=cmd, elapsed_s=time.time() - t0)
