"""GPU switches for rendering: NVENC encodes in FFmpeg and Chrome's GPU (ANGLE) backend in Remotion.

AGENTREEL_GPU (or run.py --gpu) is auto, on or off; auto is the default. auto uses the GPU only when a
short NVENC test encode succeeds, so a machine without an NVIDIA GPU (or with a broken driver) quietly
keeps the CPU path. on skips that test. off always uses the CPU path. Callers retry on the CPU if a GPU
run fails, so on never breaks a render.

Measured on an RTX 5050 laptop: NVENC encodes a 1080x1920 video about 2-3x faster than libx264
-preset medium; ANGLE makes Remotion frame rendering about 15% faster (Remotion is mostly CPU-bound).
NVENC needs about 250 MB of video memory, so it can share the GPU with the Chatterbox voice worker.
"""
from __future__ import annotations

import contextvars
import functools
import os
import shutil
import subprocess

# The web app runs several jobs in one process, so each job's choice lives in its own thread's context.
_job_mode: contextvars.ContextVar[str | None] = contextvars.ContextVar("agentreel_gpu", default=None)


def use(m: str | None) -> None:
    """Set this job's GPU mode (the Pipeline calls it with Settings.gpu); None goes back to AGENTREEL_GPU."""
    _job_mode.set(m if m in ("auto", "on", "off") else None)


def mode() -> str:
    m = (_job_mode.get() or os.environ.get("AGENTREEL_GPU") or "auto").strip().lower()
    return m if m in ("auto", "on", "off") else "auto"


def available() -> bool:
    """Whether auto would use the GPU here (an NVENC test encode works)."""
    ffmpeg = shutil.which("ffmpeg")
    return bool(ffmpeg) and _nvenc_works(ffmpeg)


@functools.cache
def _nvenc_works(ffmpeg: str) -> bool:
    try:
        cp = subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2", "-c:v",
                             "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=30)
        return cp.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def enabled() -> bool:
    if mode() != "auto":
        return mode() == "on"
    return available()


def h264_args(crf: int = 20, preset: str = "medium", gpu: bool | None = None) -> list[str]:
    """Video encoder flags for an H.264 encode. NVENC's -cq 24 matches libx264 -crf 20 by SSIM on our videos
    (files come out about 10-40% larger; adaptive quantisation is left off because it made our mostly flat
    OG frames almost twice as big for no visible gain). The CQ offset keeps other CRF values roughly in step.
    gpu=None follows the switch; False forces libx264 (the retry after a failed NVENC encode)."""
    if enabled() if gpu is None else gpu:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(crf + 4), "-b:v", "0",
                "-bf", "3", "-b_ref_mode", "middle"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]


def bitrate_args(kbps: int, gpu: bool | None = None) -> list[str]:
    """Flags for a bitrate-capped encode (used when a file is over the size limit)."""
    rate = ["-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.2)}k", "-bufsize", f"{kbps * 2}k"]
    if enabled() if gpu is None else gpu:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", *rate, "-bf", "3",
                "-b_ref_mode", "middle"]
    return ["-c:v", "libx264", "-preset", "medium", *rate]


def remotion_flags(gpu: bool | None = None) -> list[str]:
    """Chrome's ANGLE backend draws frames on the GPU (the default is a software path), and with frames off
    the CPU a little more parallelism pays off."""
    if enabled() if gpu is None else gpu:
        return ["--gl=angle", f"--concurrency={max(1, min(8, (os.cpu_count() or 2) // 2))}"]
    return [f"--concurrency={max(1, min(6, (os.cpu_count() or 2) // 2))}"]
