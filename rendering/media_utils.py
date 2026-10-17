"""FFmpeg/FFprobe helpers. Every subprocess uses argument lists, never a shell string."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


class MediaError(RuntimeError):
    pass


def tool_path(name: str) -> str | None:
    return shutil.which(name)


def require_tool(name: str) -> str:
    p = tool_path(name)
    if not p:
        raise MediaError(f"{name} was not found on PATH")
    return p


def run(cmd: list[str], timeout: float = 600, cwd: str | Path | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=cwd, env=env)


def sha256(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


@dataclass
class ProbeResult:
    path: str
    duration: float
    size_bytes: int
    format_name: str
    has_video: bool
    has_audio: bool
    video_codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    pix_fmt: str | None = None
    audio_codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    audio_bitrate: int | None = None
    raw: dict = field(default_factory=dict, repr=False)

    def summary(self) -> dict:
        d = self.__dict__.copy()
        d.pop("raw", None)
        return d


def probe(path: str | Path) -> ProbeResult:
    path = Path(path)
    if not path.is_file():
        raise MediaError(f"file does not exist: {path}")
    if path.stat().st_size == 0:
        raise MediaError(f"file is empty: {path}")
    cp = run([require_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
              str(path)], timeout=60)
    if cp.returncode != 0:
        raise MediaError(f"ffprobe failed for {path}: {cp.stderr.strip()[:500]}")
    data = json.loads(cp.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fps = None
    if v and v.get("avg_frame_rate") not in (None, "0/0"):
        try:
            fps = float(Fraction(v["avg_frame_rate"]))
        except (ValueError, ZeroDivisionError):
            fps = None
    duration = float(fmt.get("duration") or (v or a or {}).get("duration") or 0.0)
    return ProbeResult(
        path=str(path), duration=duration, size_bytes=int(fmt.get("size") or path.stat().st_size),
        format_name=fmt.get("format_name", ""), has_video=v is not None, has_audio=a is not None,
        video_codec=v.get("codec_name") if v else None, width=v.get("width") if v else None,
        height=v.get("height") if v else None, fps=fps, pix_fmt=v.get("pix_fmt") if v else None,
        audio_codec=a.get("codec_name") if a else None,
        sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        channels=a.get("channels") if a else None,
        audio_bitrate=int(a["bit_rate"]) if a and a.get("bit_rate") else None, raw=data,
    )


def audio_duration(path: str | Path) -> float:
    return probe(path).duration


def can_decode(path: str | Path, seconds: float = 3.0) -> tuple[bool, str]:
    """Decode the first few seconds to catch files ffprobe accepts but cannot play."""
    cp = run([require_tool("ffmpeg"), "-v", "error", "-t", str(seconds), "-i", str(path), "-f", "null", "-"],
             timeout=120)
    return cp.returncode == 0 and not cp.stderr.strip(), cp.stderr.strip()[:500]


def black_frame_ratio(path: str | Path, threshold: float = 0.98) -> float:
    """Fraction of the video detected as black by ffmpeg's blackdetect filter."""
    cp = run([require_tool("ffmpeg"), "-v", "info", "-i", str(path), "-vf",
              f"blackdetect=d=0.5:pic_th={threshold}:pix_th=0.02", "-an", "-f", "null", "-"], timeout=600)
    total = 0.0
    for line in cp.stderr.splitlines():
        if "black_duration:" in line:
            try:
                total += float(line.split("black_duration:")[1].split()[0])
            except (IndexError, ValueError):
                pass
    dur = probe(path).duration or 1.0
    return total / dur


def measure_loudness(path: str | Path) -> dict | None:
    """Integrated loudness (LUFS) and true peak via ffmpeg's loudnorm analysis pass."""
    cp = run([require_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
              "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], timeout=600)
    text = cp.stderr
    start, end = text.rfind("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def link_or_copy(src: Path, dst: Path) -> str:
    """Stage a file without duplicating bytes when possible (hard link), else copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            if os.path.samefile(src, dst):
                return "existing"
        except OSError:
            pass
        dst.unlink()
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"

