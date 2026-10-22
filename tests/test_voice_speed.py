"""Narration speed: the script budget follows the chosen speed, and pacing keeps the video within 3 s of the
requested length (inside 30-60 s)."""
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


def _segs(seconds, n=1):
    return [SimpleNamespace(segment_id=f"N{i:02d}", duration_s=seconds / n, word_timings=[], path="", provider="edge")
            for i in range(n)]


def _flat_layout(monkeypatch):
    import agents.editor as editor
    monkeypatch.setattr(editor, "compute_layout", lambda segs: SimpleNamespace(total_s=sum(s.duration_s for s in segs)))


def test_length_window_is_three_seconds_inside_30_to_60():
    from agents.base import length_window
    assert length_window(30) == (30, 33) and length_window(45) == (42, 48) and length_window(60) == (57, 60)


def test_pacing_slows_down_short_narration(monkeypatch):
    _flat_layout(monkeypatch)
    p = _pipe(20)
    rate, why = p._fit_rate(_segs(27.0))
    assert rate_pct(rate) < 20 and rate_pct(rate) >= 5 and "shorter" in why
    rate, why = p._fit_rate(_segs(55.0))  # 40 s target: too long, speed up but at most 15 points
    assert 20 < rate_pct(rate) <= 35 and "longer" in why
    assert p._fit_rate(_segs(40.0)) is None


def test_pacing_aims_at_the_middle_of_the_window(monkeypatch):
    # today's runs settled around 43-44 s for 45 s: the old fit aimed at 95% of the target and accepted 41.75-49.5
    _flat_layout(monkeypatch)
    p = _pipe(10, duration=45)
    rate, why = p._fit_rate(_segs(41.0))
    assert "requested 45" in why and rate_pct(rate) == 0  # 1.1 * 41 s / (1 + r) = 45 s at about +0%
    rate, _ = p._fit_rate(_segs(30.3))  # far too short: slow down as far as allowed (15 points)
    assert rate_pct(rate) == -5
    rate, _ = p._fit_rate(_segs(50.0))
    assert rate_pct(rate) == 22  # 1.1 * 50 / 45 = 1.22
    assert p._fit_rate(_segs(43.0)) is None and p._fit_rate(_segs(47.0)) is None


def test_short_narration_gets_longer_pauses_before_slowing_down(monkeypatch):
    _flat_layout(monkeypatch)
    p = _pipe(10, duration=45)
    assert p._fit_rate(_segs(42.3, n=9)) is None  # 8 pauses of up to 0.35 s cover the 2.7 s
    assert p._fit_pauses(_segs(42.3, n=9)) == 0.338
    assert p._fit_pauses(_segs(40.0, n=9)) == 0.35
    rate, _ = p._fit_rate(_segs(41.0, n=9))  # pauses add 2.8 s; the voice slows a little for the rest
    assert rate_pct(rate) == 6
    assert p._fit_pauses(_segs(43.0, n=9)) == 0.0


class _ScriptLLM:
    """Stub LLM that returns scripts of the given word counts in turn."""
    def __init__(self, *counts):
        self.counts, self.calls = list(counts), []

    def complete_json(self, *, schema, user, system, **kw):
        n = self.counts[min(len(self.calls), len(self.counts) - 1)]
        self.calls.append(user)
        words = ["Light", "bends", "inside", "falling", "raindrops", "and", "splits", "into", "colors."]
        segs, left = [], n
        while left > 0:
            k = min(10, left)
            segs.append({"text": " ".join((words * 3)[:k]), "beat": "point"})
            left -= k
        return SimpleNamespace(data=schema.model_validate({"title": "Rainbows", "segments": segs}))


def _script_run(make_ctx, llm, **brief):
    # these numbers are the Edge calibration; Chatterbox only scales the budget (see test_chatterbox_pace)
    from agents import planner, scriptwriter
    from schemas.artifacts import Facts
    first = make_ctx(dev_short=False, duration_s=45)
    first.settings.tts_provider = "edge"
    plan = planner.run(first)
    ctx = make_ctx("AI_PREFERRED", llm=llm, **{"dev_short": False, "duration_s": 45, "speed": 10, **brief})
    return ctx, scriptwriter.run(ctx, plan, Facts())


def test_short_script_is_sent_back_until_it_fits(make_ctx):
    from agents.base import words_budget
    llm = _ScriptLLM(75, 104)  # Gemini flash-lite's usual short draft, then a full-length one
    ctx, s = _script_run(make_ctx, llm)
    budget = words_budget(45, "og", 10)
    assert len(llm.calls) == 2 and s.word_count == 104 and s.word_count >= budget * 0.85
    assert f"about {budget}" in llm.calls[1] and "add about" in llm.calls[1]


def test_stubbornly_short_script_keeps_longest_draft(make_ctx):
    llm = _ScriptLLM(60, 80, 70)
    ctx, s = _script_run(make_ctx, llm)
    assert len(llm.calls) == 2 and s.word_count == 80  # one length retry, longest kept, pacing fills the rest


def test_long_enough_script_needs_one_call(make_ctx):
    llm = _ScriptLLM(100)
    _, s = _script_run(make_ctx, llm)
    assert len(llm.calls) == 1 and s.word_count == 100


def test_script_is_rewritten_once_when_pacing_cannot_reach_the_window(monkeypatch):
    _flat_layout(monkeypatch)
    p = _pipe(10, duration=45)
    state = {}
    p.job = SimpleNamespace(state=state, set=lambda **kw: state.update(kw), exists=lambda name: False,
                            log=SimpleNamespace(log=lambda *a, **kw: None))
    p.ctx.llm = object()
    p.ctx.settings.execution_mode = "AI_PREFERRED"
    script = SimpleNamespace(word_count=70)
    fb = p._length_miss(script, SimpleNamespace(segments=_segs(28.0, n=6)))  # 70 words in 28 s at +10%
    assert fb and "42-48 seconds" in fb[0] and p.ctx.words_target == state["words_target"]
    assert 105 <= state["words_target"] <= 112 and p.ctx.word_budget == state["words_target"]
    assert p._length_miss(script, SimpleNamespace(segments=_segs(28.0, n=6))) is None  # only once
    state.clear()
    assert p._length_miss(script, SimpleNamespace(segments=_segs(44.0, n=6))) is None  # inside the window: no rewrite
