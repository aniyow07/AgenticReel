"""Narration speed: the script budget follows the chosen speed, and pacing keeps narration within 30-60 s."""
from types import SimpleNamespace

from agents.base import AgentContext, rate_pct, words_budget
from orchestrator import Pipeline
from schemas.brief import Brief


def test_rate_parsing_and_budget():
    assert rate_pct("+10%") == 10 and rate_pct("-5%") == -5 and rate_pct("fast") == 0
    # a 10% faster voice needs about 10% more words to fill the same 40 seconds
    assert words_budget(40, "og", 10) > words_budget(40, "og", 0) * 1.08


def test_brief_speed_overrides_setting():
    brief = Brief.model_validate({"topic": "Why the sky is blue", "speed": 20})
    ctx = AgentContext(job=None, brief=brief, settings=SimpleNamespace(tts_rate="+10%"), llm=None)
    assert ctx.base_rate == "+20%" and ctx.speed_pct == 20
    ctx2 = AgentContext(job=None, brief=Brief.model_validate({"topic": "Why the sky is blue"}),
                        settings=SimpleNamespace(tts_rate="+10%"), llm=None)
    assert ctx2.base_rate == "+10%"


def _pipe(speed, duration=40):
    p = Pipeline.__new__(Pipeline)
    p.brief = Brief.model_validate({"topic": "Why the sky is blue", "speed": speed, "duration_s": duration})
    p.ctx = AgentContext(job=None, brief=p.brief, settings=SimpleNamespace(tts_rate="+10%"), llm=None)
    return p


def _segs(seconds):
    return [SimpleNamespace(segment_id="N01", duration_s=seconds, word_timings=[], path="", provider="edge")]


def test_pacing_slows_down_short_narration(monkeypatch):
    import agents.editor as editor
    p = _pipe(20)
    monkeypatch.setattr(editor, "compute_layout", lambda segs: SimpleNamespace(total_s=segs[0].duration_s))
    rate, why = p._fit_rate(_segs(27.0))
    assert rate_pct(rate) < 20 and rate_pct(rate) >= 5 and "shorter" in why
    rate, why = p._fit_rate(_segs(55.0))  # 40 s target: too long, speed up but at most 15 points
    assert 20 < rate_pct(rate) <= 35 and "longer" in why
    assert p._fit_rate(_segs(38.0)) is None
