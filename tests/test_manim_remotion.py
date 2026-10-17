"""Real Manim and Remotion renders (marked slow)."""
import pytest

from rendering import manim_runner, remotion_runner
from rendering.media_utils import link_or_copy, probe
from schemas.render_props import RenderProps


@pytest.mark.parametrize("params", [
    {"template": "process_diagram", "steps": ["only one"]},
    {"template": "simple_chart", "labels": ["a", "b"], "values": [1]},
    {"template": "simple_chart", "labels": ["a"], "values": [float("nan")]},
    {"template": "os_system", "cmd": "whoami"},
])
def test_manim_rejects_invalid_or_unknown_templates(params, tmp_path):
    r = manim_runner.render(params, tmp_path, "x")
    assert not r.ok and "invalid parameters" in r.error


@pytest.mark.slow
def test_manim_clip_renders_and_is_used_by_remotion_og(tmp_path):
    clip = manim_runner.render({"template": "timeline", "title": "Test timeline",
                                "events": [{"label": "Start"}, {"label": "Middle"}, {"label": "End"}],
                                "duration_s": 3}, tmp_path / "manim", "clip", size=(360, 360))
    assert clip.ok and clip.duration_s > 2 and (tmp_path / "manim" / "clip.mp4").exists()
    pub = tmp_path / "public"
    link_or_copy(tmp_path / "manim" / "clip.mp4", pub / "manim" / "clip.mp4")
    props = RenderProps.model_validate({
        "mode": "og", "fps": 30, "width": 270, "height": 480, "durationInFrames": 60,
        "safeZone": {"top": 60, "bottom": 90},
        "captions": [{"id": "c1", "text": "Manim in Remotion", "startFrame": 0, "endFrame": 60}],
        "scenes": [{"id": "s1", "startFrame": 0, "durationInFrames": 60, "visualType": "manim",
                    "params": {"src": "manim/clip.mp4", "clipDurationInFrames": int(clip.duration_s * 30) - 1}}]})
    res = remotion_runner.render(props, pub, tmp_path / "props.json", tmp_path / "out.mp4")
    assert res.ok, res.log_tail
    assert probe(tmp_path / "out.mp4").duration == pytest.approx(2.0, abs=0.1)


@pytest.mark.slow
def test_remotion_reports_missing_staged_media(tmp_path):
    props = RenderProps.model_validate({
        "mode": "minecraft", "fps": 30, "width": 270, "height": 480, "durationInFrames": 30,
        "background": [{"src": "gameplay/missing.mp4", "startFrame": 0, "durationInFrames": 30}]})
    res = remotion_runner.render(props, tmp_path / "public", tmp_path / "p.json", tmp_path / "o.mp4")
    assert not res.ok and "staged media missing" in res.error


@pytest.mark.slow
def test_remotion_render_failure_is_reported(tmp_path, monkeypatch):
    """Zod rejects props that bypassed Pydantic; the runner must report the failure, not success.
    (Remotion merges input props over defaultProps, so the bad value must be an invalid one, not a missing one.)"""
    props = RenderProps.model_validate({
        "mode": "og", "fps": 30, "width": 270, "height": 480, "durationInFrames": 30,
        "scenes": [{"id": "s", "startFrame": 0, "durationInFrames": 30, "visualType": "title",
                    "params": {"title": "x"}}]})
    monkeypatch.setattr(RenderProps, "model_dump_json", lambda self, **k: '{"mode": "og", "fps": 5, "durationInFrames": -1}')
    res = remotion_runner.render(props, tmp_path / "pub", tmp_path / "p.json", tmp_path / "o.mp4")
    assert not res.ok and res.returncode not in (None, 0)
