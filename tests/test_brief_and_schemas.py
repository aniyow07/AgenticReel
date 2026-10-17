import pytest
from pydantic import ValidationError

from schemas.artifacts import Fact, Script, ScriptSegment, Storyboard
from schemas.brief import Brief, load_brief
from schemas.render_props import ImageParams, RenderProps


def test_valid_brief_defaults():
    b = Brief(topic="Explain green hydrogen", duration_s=45)
    assert b.mode == "og" and b.portrait and b.is_factual


@pytest.mark.parametrize("dur", [10, 29, 61, 120])
def test_production_duration_enforced(dur):
    with pytest.raises(ValidationError):
        Brief(topic="Anything at all", duration_s=dur)


def test_dev_short_allows_short_but_not_tiny():
    assert Brief(topic="Anything at all", duration_s=10, dev_short=True).dev_short
    with pytest.raises(ValidationError):
        Brief(topic="Anything at all", duration_s=2, dev_short=True)


@pytest.mark.parametrize("field,value", [("mode", "tiktok"), ("format", "square"), ("content_type", "x"),
                                         ("id", "../evil"), ("unknown_field", 1)])
def test_invalid_fields_rejected(field, value):
    with pytest.raises(ValidationError):
        Brief.model_validate({"topic": "Topic here", "duration_s": 40, field: value})


def test_load_brief_resolves_sources(tmp_path):
    (tmp_path / "s.md").write_text("# x\nhello", encoding="utf-8")
    p = tmp_path / "b.yaml"
    p.write_text("topic: Arbitrary user topic\nmode: subway\nduration_s: 40\nsource_files: [s.md]\n", encoding="utf-8")
    b = load_brief(p)
    assert b.mode == "subway" and b.source_files[0].endswith("s.md")


def test_supported_fact_requires_evidence():
    with pytest.raises(ValidationError):
        Fact(fact_id="F1", claim="Something true", status="supported")
    Fact(fact_id="F1", claim="Something unproven", status="unsupported")


def test_script_unique_segment_ids():
    seg = ScriptSegment(segment_id="N01", text="hello there")
    with pytest.raises(ValidationError):
        Script(title="T1", segments=[seg, seg])


def test_storyboard_rejects_wrong_visual_for_mode():
    scene = {"scene_id": "S1", "start_time": 0, "duration": 3, "narration_segment_ids": ["N01"],
             "visual_type": "key_points", "visual_parameters": {"points": ["a"]}}
    with pytest.raises(ValidationError):
        Storyboard(mode="minecraft", scenes=[scene])
    Storyboard(mode="og", scenes=[scene])
    with pytest.raises(ValidationError):
        Storyboard(mode="og", scenes=[{**scene, "visual_type": "python_code"}])


def test_storyboard_timing_validation():
    script = Script(title="T1", segments=[ScriptSegment(segment_id="N01", text="one two"),
                                          ScriptSegment(segment_id="N02", text="three four")])
    sb = Storyboard(mode="og", scenes=[
        {"scene_id": "S1", "start_time": 0, "duration": 5, "narration_segment_ids": ["N01"], "visual_type": "title",
         "visual_parameters": {"title": "x"}},
        {"scene_id": "S2", "start_time": 7, "duration": 5, "narration_segment_ids": ["N02"],
         "visual_type": "title", "visual_parameters": {"title": "y"}}])
    issues = sb.validate_against(script, 12)
    assert any("gap/overlap" in i for i in issues)


@pytest.mark.parametrize("bad", ["C:/Windows/x.png", "/etc/passwd", "../x.png", "a/../../x.png", "https://x/y.png"])
def test_render_media_paths_must_be_public_relative(bad):
    with pytest.raises(ValidationError):
        ImageParams(src=bad)


def test_render_props_consistency():
    base = {"mode": "minecraft", "fps": 30, "width": 540, "height": 960, "durationInFrames": 90}
    with pytest.raises(ValidationError, match="gameplay"):
        RenderProps.model_validate(base)
    with pytest.raises(ValidationError, match="past the video end"):
        RenderProps.model_validate({**base, "background": [{"src": "g.mp4", "startFrame": 0, "durationInFrames": 90}],
                                    "captions": [{"id": "c", "text": "x", "startFrame": 0, "endFrame": 120}]})
