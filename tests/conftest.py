import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Tests never call the real OpenRouter API.
os.environ.pop("OPENROUTER_API_KEY", None)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: renders real media (Manim/Remotion/FFmpeg)")


@pytest.fixture
def settings(tmp_path):
    from core.config import Settings

    s = Settings(outputs_dir=tmp_path / "outputs")
    s.outputs_dir.mkdir(parents=True, exist_ok=True)
    return s


@pytest.fixture
def job(tmp_path):
    from core.jobs import Job

    return Job(tmp_path / "outputs", "test-job")


@pytest.fixture
def make_ctx(job, settings):
    from agents.base import AgentContext
    from schemas.brief import Brief

    def _make(exec_mode="LOCAL_ONLY", llm=None, **brief):
        settings.execution_mode = exec_mode
        b = Brief.model_validate({"topic": "Why do people procrastinate?", "dev_short": True, "duration_s": 12,
                                  **brief})
        return AgentContext(job=job, brief=b, settings=settings, llm=llm)
    return _make


@pytest.fixture
def synthetic_clip(tmp_path):
    """A synthetic test pattern for renderer/validation unit tests only. It is NOT gameplay."""
    out = tmp_path / "synthetic_testsrc.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:rate=30:duration=6", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


