import pytest

from core.config import Settings
from rendering import gpu


@pytest.fixture(autouse=True)
def _no_job_override():
    gpu.use(None)
    yield
    gpu.use(None)


def test_off_keeps_the_cpu_path(monkeypatch):
    monkeypatch.setenv("AGENTREEL_GPU", "off")
    assert not gpu.enabled()
    assert gpu.h264_args(20, "medium")[:2] == ["-c:v", "libx264"]
    assert "-crf" in gpu.h264_args(20, "medium")
    assert gpu.bitrate_args(900)[:2] == ["-c:v", "libx264"]
    assert not any(f.startswith("--gl") for f in gpu.remotion_flags())


def test_on_uses_nvenc_and_angle(monkeypatch):
    monkeypatch.setenv("AGENTREEL_GPU", "on")
    assert gpu.enabled()
    args = gpu.h264_args(20)
    assert args[:2] == ["-c:v", "h264_nvenc"] and args[args.index("-cq") + 1] == "24"
    assert "--gl=angle" in gpu.remotion_flags()
    assert gpu.h264_args(20, gpu=False)[:2] == ["-c:v", "libx264"]  # the CPU retry
    assert gpu.bitrate_args(900, gpu=False)[:2] == ["-c:v", "libx264"]


def test_auto_falls_back_without_nvenc(monkeypatch):
    monkeypatch.setenv("AGENTREEL_GPU", "auto")
    monkeypatch.setattr(gpu, "_nvenc_works", lambda ffmpeg: False)
    assert not gpu.enabled()
    monkeypatch.setattr(gpu.shutil, "which", lambda name: None)
    assert not gpu.enabled()


def test_unknown_value_means_auto(monkeypatch):
    monkeypatch.setenv("AGENTREEL_GPU", "maybe")
    assert gpu.mode() == "auto"


def test_a_job_setting_beats_the_environment(monkeypatch):
    monkeypatch.setenv("AGENTREEL_GPU", "on")
    assert Settings.from_env().gpu == "on"
    gpu.use("off")  # what the Pipeline does with Settings.gpu for one job
    assert not gpu.enabled()
    gpu.use("bogus")
    assert gpu.mode() == "on"
