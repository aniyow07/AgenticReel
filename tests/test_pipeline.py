import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator import Pipeline
from schemas.artifacts import QACheck, QAReport
from schemas.brief import Brief


def _brief(**kw):
    return Brief.model_validate({"topic": "Why do people procrastinate?", "duration_s": 10, "dev_short": True, **kw})


def test_critic_repair_loop_is_bounded(settings, monkeypatch):
    settings.execution_mode = "LOCAL_ONLY"
    settings.max_repair_attempts = 2
    p = Pipeline(_brief(), settings=settings)
    settings.execution_mode = "AI_PREFERRED"
    p.ctx.llm = SimpleNamespace(job_cost=0.0, calls=0)  # pretend an LLM is available so script repairs are meaningful
    calls = {"script": 0, "qa": 0}
    monkeypatch.setattr(p, "plan", lambda: "plan")
    monkeypatch.setattr(p, "research", lambda plan: "facts")

    def script(plan, facts, feedback=None):
        calls["script"] += 1
        return "script"
    monkeypatch.setattr(p, "script", script)
    monkeypatch.setattr(p, "storyboard", lambda *a: "sb")
    monkeypatch.setattr(p, "assets_and_audio", lambda *a: "manifest")
    monkeypatch.setattr(p, "edit_and_render", lambda *a: ("props", {}))

    def qa(*a, **k):
        calls["qa"] += 1
        return QAReport(technical_pass=False, semantic_status="not_reviewed", checks=[
            QACheck(name="claims_supported", passed=False, detail="bad claim", route_to="scripting")])
    monkeypatch.setattr(p, "qa", qa)
    report = p.run()
    assert calls == {"script": 3, "qa": 3}  # first run + 2 repairs, then stop
    assert p.job.state["status"] == "failed_qa" and p.job.state["repairs"] == 2
    assert "automatic repair #2" in p.job.log.interventions.read_text()


def test_local_only_does_not_repeat_deterministic_repairs(settings, monkeypatch):
    settings.execution_mode = "LOCAL_ONLY"
    p = Pipeline(_brief(), settings=settings)
    n = {"qa": 0}
    for name, val in [("plan", lambda: 1), ("research", lambda *a: 1), ("script", lambda *a: 1),
                      ("storyboard", lambda *a: 1), ("assets_and_audio", lambda *a: 1),
                      ("edit_and_render", lambda *a: (1, {}))]:
        monkeypatch.setattr(p, name, val)

    def qa(*a, **k):
        n["qa"] += 1
        return QAReport(technical_pass=False, semantic_status="not_reviewed", checks=[
            QACheck(name="duration_target", passed=False, detail="too short", route_to="scripting")])
    monkeypatch.setattr(p, "qa", qa)
    p.run()
    assert n["qa"] == 1 and any("same result" in x for x in p.job.state["notes"])


def test_resume_reuses_completed_stages(settings):
    settings.execution_mode = "LOCAL_ONLY"
    p = Pipeline(_brief(), settings=settings)
    plan = p.plan()
    p.research(plan)
    p2 = Pipeline(job_id=p.job.id, settings=settings)
    p2.plan()
    p2.research(plan)
    reused = [e for e in p2.job.log.entries() if e["status"] == "reused"]
    assert {e["stage"] for e in reused} == {"planning", "research"}


def test_inputs_are_copied_and_limited(settings, tmp_path):
    settings.execution_mode = "LOCAL_ONLY"
    src = tmp_path / "my notes.md"
    src.write_text("# x\nsome text", encoding="utf-8")
    p = Pipeline(_brief(source_files=[str(src)]), settings=settings)
    assert Path(p.brief.source_files[0]).parent == p.job.dir / "inputs"
    assert Path(p.brief.source_files[0]).name == "my_notes.md"


@pytest.mark.slow
def test_e2e_local_only_og_without_api_key(settings):
    """Full pipeline, no OpenRouter key, real TTS + Remotion + FFmpeg (+ Manim when planned)."""
    settings.execution_mode = "LOCAL_ONLY"
    assert not os.environ.get("OPENROUTER_API_KEY")
    src = Path(__file__).resolve().parent.parent / "briefs" / "sources" / "green_hydrogen_primer.md"
    p = Pipeline(_brief(topic="Explain green hydrogen", mode="og", source_files=[str(src)], duration_s=15),
                 settings=settings)
    report = p.run()
    assert report.technical_pass, [c for c in report.failures]
    assert report.is_test_render
    assert p.job.path("final.mp4").exists() and p.job.path("captions.srt").exists()
    assert not any(e["tool"] == "openrouter" and e["status"] == "ok" for e in p.job.log.entries())


@pytest.mark.slow
def test_e2e_missing_gameplay_is_clear_error(settings, monkeypatch, tmp_path):
    from core import gameplay

    monkeypatch.setattr(gameplay, "MANIFEST", tmp_path / "empty_manifest.csv")
    settings.execution_mode = "LOCAL_ONLY"
    p = Pipeline(_brief(mode="subway", content_type="fictional_story", topic="A ghost on the night train"),
                 settings=settings)
    with pytest.raises(Exception, match="No usable subway gameplay"):
        p.run()
    assert p.job.state["status"] == "failed"
    assert p.job.state["stages"]["assets"]["status"] == "failed"
    assert not p.job.path("final.mp4").exists()


def test_same_brief_and_sources_reuse_content_across_jobs(settings, tmp_path):
    settings.execution_mode = "LOCAL_ONLY"
    src = tmp_path / "notes.md"
    src.write_text("# Notes\nBees make honey from flower nectar stored in the hive.", encoding="utf-8")
    b = _brief(topic="How bees make honey", source_files=[str(src)])
    p1 = Pipeline(b, settings=settings)
    plan = p1.plan()
    facts = p1.research(plan)
    s1 = p1.script(plan, facts)
    # another version: different mode and voice, same brief + same PDF -> plan/research/script reused
    p2 = Pipeline(b.model_copy(update={"mode": "subway", "voice": "en-US-GuyNeural"}), settings=settings)
    plan2 = p2.plan()
    s2 = p2.script(plan2, p2.research(plan2))
    assert plan2.mode == "subway" and s2.segments == s1.segments
    reused = {e["stage"] for e in p2.job.log.entries() if e["tool"] == "content_cache"}
    assert reused == {"planning", "research", "scripting"}
    # changed source file -> different key, nothing reused
    src.write_text("# Notes\nSomething else entirely about wasps.", encoding="utf-8")
    p3 = Pipeline(b, settings=settings)
    p3.plan()
    assert not any(e["tool"] == "content_cache" for e in p3.job.log.entries())
    # explicit fresh script
    src.write_text("# Notes\nBees make honey from flower nectar stored in the hive.", encoding="utf-8")
    p4 = Pipeline(b, settings=settings, reuse_content=False)
    p4.plan()
    assert not any(e["tool"] == "content_cache" for e in p4.job.log.entries())


def test_voice_is_validated():
    with pytest.raises(Exception):
        _brief(voice="rm -rf /")
    assert _brief(voice="en-IN-PrabhatNeural").voice == "en-IN-PrabhatNeural"
