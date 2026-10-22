import json
from pathlib import Path

import pytest

from agents import planner, researcher, scriptwriter, storyboarder
from agents.base import AgentFailure, ask_llm
from core.jobs import Job, fingerprint, safe_filename
from schemas.artifacts import Facts, Plan


def test_job_paths_cannot_escape(job):
    with pytest.raises(ValueError):
        job.path("../../etc/passwd")
    with pytest.raises(ValueError):
        Job(job.dir.parent, "../escape")
    assert safe_filename("..\\..\\evil name.pdf") == "evil_name.pdf"


def test_stage_cache_and_resume(job):
    fp = fingerprint({"a": 1})
    job.write_json("plan.json", {"x": 1})
    job.stage_done("planning", fp=fp, artifacts=["plan.json"])
    assert job.cached("planning", fp)
    assert not job.cached("planning", fingerprint({"a": 2}))  # inputs changed
    reloaded = Job(job.dir.parent, job.id)  # simulate a new process resuming
    assert reloaded.cached("planning", fp)
    job.path("plan.json").unlink()
    assert not job.cached("planning", fp)  # artifact missing -> rerun


def test_invalidate_from_marks_downstream_stale(job):
    for s in ("planning", "research", "scripting", "storyboarding"):
        job.stage_done(s, fp="x", artifacts=[])
    job.invalidate_from("scripting")
    st = job.state["stages"]
    assert st["research"]["status"] == "done" and st["scripting"]["status"] == "stale"
    assert st["storyboarding"]["status"] == "stale"


def test_local_only_never_calls_llm(make_ctx):
    class Boom:
        def complete_json(self, **kw):
            raise AssertionError("LLM must not be called in LOCAL_ONLY")
    ctx = make_ctx("LOCAL_ONLY", llm=Boom())
    assert ask_llm(ctx, "planning", "s", "u", Plan, "v") is None
    plan = planner.run(ctx)
    assert plan.origin == "local"


def test_ai_required_fails_clearly_without_llm(make_ctx):
    ctx = make_ctx("AI_REQUIRED", llm=None)
    with pytest.raises(AgentFailure, match="AI_REQUIRED"):
        planner.run(ctx)


def test_ai_preferred_falls_back_and_records_note(make_ctx):
    from providers.openrouter import LLMUnavailable

    class Down:
        def complete_json(self, **kw):
            raise LLMUnavailable("all configured models failed")
    ctx = make_ctx("AI_PREFERRED", llm=Down())
    plan = planner.run(ctx)
    assert plan.origin == "local" and any("fallback" in n for n in ctx.notes)


def test_research_without_sources_reports_limitation(make_ctx):
    ctx = make_ctx()
    facts = researcher.run(ctx, planner.run(ctx))
    assert not facts.supported() and any("No source documents" in x for x in facts.limitations)


def test_llm_unsupported_claims_are_flagged(make_ctx, tmp_path):
    src = tmp_path / "s.md"
    src.write_text("# Sleep\nAdults generally need seven or more hours of sleep per night.", encoding="utf-8")

    class FakeLLM:
        def complete_json(self, *, schema, **kw):
            data = schema.model_validate({"claims": [
                {"claim": "Adults generally need seven or more hours of sleep per night.", "passage": 1},
                {"claim": "Sleeping 12 hours doubles your IQ.", "passage": 1}]})
            return type("C", (), {"data": data})()
    ctx = make_ctx("LOCAL_ONLY", topic="How much sleep do adults need?", source_files=[str(src)])
    plan = planner.run(ctx)
    ctx.settings.execution_mode, ctx.llm = "AI_PREFERRED", FakeLLM()
    facts = researcher.run(ctx, plan)
    assert facts.origin == "llm"
    by_claim = {f.claim: f for f in facts.facts}
    assert by_claim["Adults generally need seven or more hours of sleep per night."].status == "supported"
    assert by_claim["Sleeping 12 hours doubles your IQ."].status == "unsupported"


def test_script_checks_catch_invented_numbers(make_ctx):
    ctx = make_ctx()
    from schemas.artifacts import Script, ScriptSegment
    s = Script(title="T1", segments=[ScriptSegment(segment_id="N01", text="Over 87 percent of people agree.")])
    issues = scriptwriter.check_script(s, Facts(), ctx)
    assert any("87" in i for i in issues)
    repaired = scriptwriter.remove_unsupported(
        Script(title="T1", segments=[*s.segments, ScriptSegment(segment_id="N02", text="Fine sentence here."),
                                     ScriptSegment(segment_id="N03", text="Another fine one.")]), issues)
    assert [x.segment_id for x in repaired.segments] == ["N02", "N03"]


def test_invalid_llm_storyboard_is_sanitised(make_ctx):
    ctx = make_ctx(mode="og")
    plan = planner.run(ctx)
    facts = Facts()
    script = scriptwriter.run(ctx, plan, facts)
    ids = [s.segment_id for s in script.segments]
    bad = storyboarder.StoryboardLLM(scenes=[
        storyboarder.SceneLLM(segment_ids=ids[:1], visual_type="exec_python", visual_parameters={"code": "rm -rf"}),
        storyboarder.SceneLLM(segment_ids=ids[1:2], visual_type="stat", visual_parameters={"value": 99, "label": "x"}),
        storyboarder.SceneLLM(segment_ids=ids[2:], visual_type="manim",
                              manim_template={"template": "evil_template", "code": "import os"}),
    ])
    fixed, notes = storyboarder.sanitize(ctx, storyboarder.fix_coverage(bad, script), script, facts)
    types = [s.visual_type for s in fixed.scenes]
    assert "exec_python" not in types and "stat" not in types and "manim" not in types
    assert len(notes) == 3
    sb = storyboarder.to_storyboard(ctx, fixed, script, "llm")
    assert sb.validate_against(script, ctx.brief.duration_s, tol=0.05) == []



def test_at_most_two_3d_scenes(make_ctx):
    ctx = make_ctx(mode="og")
    plan = planner.run(ctx)
    facts = Facts()
    script = scriptwriter.run(ctx, plan, facts)
    ids = [s.segment_id for s in script.segments]
    assert len(ids) >= 3
    tpls = [{"template": "solids_3d", "title": "Shapes", "shapes": ["cube"]}, {"template": "galaxy_3d", "title": "G"},
            {"template": "wave_3d", "title": "Waves", "kind": "transverse"}]
    sb = storyboarder.StoryboardLLM(scenes=[
        storyboarder.SceneLLM(segment_ids=ids[i:i + 1] if i < 2 else ids[2:], visual_type="manim",
                              manim_template=dict(t)) for i, t in enumerate(tpls)])
    fixed, notes = storyboarder.sanitize(ctx, storyboarder.fix_coverage(sb, script), script, facts)
    kept = [s.manim_template["template"] for s in fixed.scenes if s.visual_type == "manim"]
    assert kept == ["solids_3d", "wave_3d"]  # the middle one would have been a second 3D scene in a row
    assert len(kept) <= storyboarder.MAX_3D_SCENES and any("3D" in n for n in notes)


def test_picker_never_repeats_a_template(make_ctx):
    """A template is used once per video; the repeat keeps its data as a Remotion visual."""
    ctx = make_ctx(mode="og")
    plan = planner.run(ctx)
    facts = Facts()
    script = scriptwriter.run(ctx, plan, facts)
    ids = [s.segment_id for s in script.segments]
    cyc = {"template": "cycle_diagram", "title": "Loop", "stages": ["Plan", "Do", "Check"]}
    tpls = [cyc, dict(cyc), {"template": "solids_3d", "title": "S", "shapes": ["cube"]}]
    sb = storyboarder.StoryboardLLM(scenes=[
        storyboarder.SceneLLM(segment_ids=ids[i:i + 1] if i < 2 else ids[2:], visual_type="manim",
                              manim_template=dict(t)) for i, t in enumerate(tpls)])
    fixed, notes = storyboarder.sanitize(ctx, storyboarder.fix_coverage(sb, script), script, facts)
    kept = [s.manim_template["template"] for s in fixed.scenes if s.visual_type == "manim"]
    assert kept == ["cycle_diagram", "solids_3d"]
    assert any("already used" in n for n in notes)
    assert fixed.scenes[1].visual_type in ("key_points", "process", "text_reveal")


def test_catalog_covers_every_template_and_shuffles():
    from agents import template_catalog as tc
    from rendering import manim_runner
    assert set(tc.BY_NAME) == set(manim_runner.TEMPLATES)
    firsts = {tc.catalog_text(seed).splitlines()[1].split(":")[0].strip() for seed in range(20)}
    assert len(firsts) >= 5  # no template sits at the top of the list for every video
    assert "domino_chain" in tc.suggest("the chain of causes that led to the 2008 crash")
    from collections import Counter
    fresh = tc.suggest("five myths about sleep habits", Counter())
    tired = tc.suggest("five myths about sleep habits", Counter({fresh[0]: 3}))
    assert fresh[0] != tired[0]  # heavy recent use pushes a template down the list

def test_brainrot_storyboard_is_gameplay_only(make_ctx):
    ctx = make_ctx(mode="subway", content_type="fictional_story", topic="A ghost story on a train")
    plan = planner.run(ctx)
    script = scriptwriter.run(ctx, plan, Facts())
    sb = storyboarder.run(ctx, plan, script, Facts())
    assert {s.visual_type for s in sb.scenes} == {"gameplay"}
    assert plan.manim_scenes == []



def test_on_screen_text_is_grounded_in_sources():
    from agents.storyboarder import ground_params
    from retrieval.index import tokenize
    src = "Skills: Python, PyTorch, Pandas. Built Halo in Rust. LinkedIn profile available."
    g = {"text": src.lower(), "tokens": set(tokenize(src)), "numbers": src}
    p, notes = ground_params("key_points", {"heading": "Skills", "points": ["Python", "TensorFlow", "Scikit-learn",
                                                                              "PyTorch", "Cut costs by 90%"]},
                             g, "He codes in Python.", "")
    assert p["points"] == ["Python", "PyTorch"] and len(notes) == 3
    p, notes = ground_params("end_card", {"text": "Say hi", "cta": "Visit linkedin.com/in/made-up"}, g, "",
                             "Connect on LinkedIn")
    assert "linkedin.com" not in p["cta"] and p["cta"] == "Connect on LinkedIn"


def test_motion_levels_rule_and_captions():
    from agents.editor import with_motion
    from agents.storyboarder import rule_motion
    from rendering.timeline import TimedCaption
    from schemas.artifacts import Script, ScriptSegment, Storyboard
    script = Script(title="T1", segments=[ScriptSegment(segment_id="N01", text="Wait, what?"),
                                          ScriptSegment(segment_id="N02", text="It was a normal day."),
                                          ScriptSegment(segment_id="N03", text="Then it moved!"),
                                          ScriptSegment(segment_id="N04", text="The end.")])
    lv = rule_motion(script)
    assert lv == {"N01": "hit", "N02": "normal", "N03": "strong", "N04": "calm"}
    sb = Storyboard(mode="subway", scenes=[{"scene_id": "S1", "start_time": 0, "duration": 4,
                                            "narration_segment_ids": ["N01", "N02", "N03", "N04"],
                                            "visual_type": "gameplay", "visual_parameters": {"motion": lv}}])
    caps = [TimedCaption(id=f"c{i}", text="x y", start=i, end=i + 0.9, segment_id=s, alignment="tts_word_boundaries")
            for i, s in enumerate(["N01", "N01", "N02", "N03", "N04"])]
    frames = [{"id": c.id} for c in caps]
    assert [f["motion"] for f in with_motion(frames, caps, sb)] == [3, 1, 1, 2, 0]  # 2nd phrase of N01 no repeat hit
