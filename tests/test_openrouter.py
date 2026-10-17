"""OpenRouter client behaviour with a mocked HTTP transport (no real API calls, no spend)."""
import json

import httpx
import pytest
from pydantic import BaseModel

from core.runlog import RunLogger
from providers.openrouter import (AuthError, BudgetExceeded, LLMUnavailable, OpenRouterClient, QuotaExhausted,
                                  SpendLedger, extract_json)

MODELS = {"data": [
    {"id": "free/a:free", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["response_format"]},
    {"id": "free/b:free", "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": []},
    {"id": "paid/c", "pricing": {"prompt": "0.000001", "completion": "0.000002"}, "supported_parameters": []},
]}


class Answer(BaseModel):
    answer: str


def ok(content, cost=None, model="free/a:free"):
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    if cost is not None:
        usage["cost"] = cost
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": content}}], "usage": usage})


def make(settings, tmp_path, handler, primary="free/a:free", fallbacks=("free/b:free",), **kw):
    settings.openrouter_api_key = "test-key"
    settings.openrouter_model = primary
    settings.openrouter_fallback_models = list(fallbacks)
    for k, v in kw.items():
        setattr(settings, k, v)
    calls = []

    def route(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS)
        body = json.loads(req.content)
        calls.append(body["model"])
        assert req.headers["Authorization"] == "Bearer test-key"
        return handler(body, len(calls))
    client = httpx.Client(transport=httpx.MockTransport(route))
    log = RunLogger("j", tmp_path / "logs")
    c = OpenRouterClient(settings, logger=log, client=client, sleep=lambda s: None,
                         ledger=SpendLedger(tmp_path / "ledger.json"))
    return c, calls, log


def ask(c):
    return c.complete_json(stage="t", system="s", user="u", schema=Answer, prompt_version="test/v1")


def test_success_and_logging(settings, tmp_path):
    c, calls, log = make(settings, tmp_path, lambda b, n: ok('{"answer": "hi"}', cost=0.0))
    r = ask(c)
    assert r.data.answer == "hi" and r.cost_basis == "measured" and calls == ["free/a:free"]
    entries = log.entries()
    assert entries[-1]["status"] == "ok" and entries[-1]["prompt_version"] == "test/v1"
    assert "test-key" not in log.run_log.read_text()


def test_429_is_bounded_then_falls_back(settings, tmp_path):
    def h(body, n):
        if body["model"] == "free/a:free":
            return httpx.Response(429, json={"error": {"code": 429, "message": "rate limited"}})
        return ok('{"answer": "from fallback"}', model="free/b:free")
    c, calls, _ = make(settings, tmp_path, h, llm_max_retries=2)
    r = ask(c)
    assert r.data.answer == "from fallback"
    assert calls.count("free/a:free") == 3  # 1 try + 2 bounded retries, never endless


def test_all_models_rate_limited_fails_clearly(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: httpx.Response(429, json={}), llm_max_retries=1)
    with pytest.raises(LLMUnavailable, match="all configured models failed"):
        ask(c)
    assert len(calls) == 4  # 2 models x (1 + 1 retry)


def test_quota_exhausted_is_not_retried(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: httpx.Response(402, json={"error": {"message": "no credits"}}))
    with pytest.raises(QuotaExhausted):
        ask(c)
    assert len(calls) == 1


def test_bad_key(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: httpx.Response(401, json={}))
    with pytest.raises(AuthError):
        ask(c)


def test_invalid_model_id_moves_to_next(settings, tmp_path):
    def h(body, n):
        if body["model"] == "free/a:free":
            return httpx.Response(400, json={"error": {"code": 400, "message": "not a valid model ID"}})
        return ok('{"answer": "b"}')
    c, calls, _ = make(settings, tmp_path, h)
    assert ask(c).data.answer == "b" and calls == ["free/a:free", "free/b:free"]


def test_malformed_output_gets_one_repair(settings, tmp_path):
    replies = iter(["sure! here you go", '```json\n{"answer": "fixed"}\n```'])
    c, calls, log = make(settings, tmp_path, lambda b, n: ok(next(replies)))
    assert ask(c).data.answer == "fixed"
    assert [e["status"] for e in log.entries()] == ["invalid_output", "ok"]


def test_malformed_output_rejected_after_bounded_attempts(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: ok('{"wrong": 1}'), fallbacks=())
    with pytest.raises(LLMUnavailable):
        ask(c)
    assert len(calls) == 2


def test_paid_models_never_used_silently(settings, tmp_path):
    c, calls, log = make(settings, tmp_path, lambda b, n: ok('{"answer": "x"}'), primary="paid/c", fallbacks=())
    with pytest.raises(LLMUnavailable, match="paid models are disabled"):
        ask(c)
    assert calls == []
    c2, calls2, _ = make(settings, tmp_path, lambda b, n: ok('{"answer": "x"}'), primary="paid/c",
                         fallbacks=("free/b:free",))
    ask(c2)
    assert calls2 == ["free/b:free"]


def test_unknown_price_model_treated_as_paid(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: ok('{"answer": "x"}'), primary="mystery/model", fallbacks=())
    with pytest.raises(LLMUnavailable):
        ask(c)


def test_spend_limit_enforced(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: ok('{"answer": "x"}', cost=0.6, model="paid/c"),
                       primary="paid/c", fallbacks=(), allow_paid_models=True, max_api_spend_usd=1.0)
    ask(c)
    ask(c)  # ledger now 1.2 >= 1.0
    with pytest.raises(BudgetExceeded):
        ask(c)
    assert len(calls) == 2


def test_cost_estimated_when_not_reported(settings, tmp_path):
    c, _, log = make(settings, tmp_path, lambda b, n: ok('{"answer": "x"}', model="paid/c"), primary="paid/c",
                     fallbacks=(), allow_paid_models=True)
    r = ask(c)
    assert r.cost_basis == "estimated" and r.cost == pytest.approx(10 * 1e-6 + 5 * 2e-6)
    assert "estimated" in log.cost_csv.read_text()


def test_no_key():
    from core.config import Settings
    c = OpenRouterClient(Settings(openrouter_api_key=""), client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500))))
    with pytest.raises(LLMUnavailable):
        c.complete_json(stage="t", system="s", user="u", schema=Answer, prompt_version="v")


def test_extract_json_variants():
    assert extract_json('prefix {"a": 1} suffix') == {"a": 1}
    assert extract_json('```json\n[1, 2]\n```') == [1, 2]
    with pytest.raises(ValueError):
        extract_json("no json at all")


def test_reasoning_budget_and_empty_reply_retry(settings, tmp_path):
    seen = []

    def h(body, n):
        seen.append((body.get("reasoning"), body["max_tokens"]))
        return ok("" if n == 1 else '{"answer": "after retry"}', model="free/a:free")
    MODELS["data"][0]["supported_parameters"] = ["response_format", "reasoning"]
    try:
        c, calls, _ = make(settings, tmp_path, h, fallbacks=())
        assert ask(c).data.answer == "after retry"
    finally:
        MODELS["data"][0]["supported_parameters"] = ["response_format"]
    assert seen[0][0] == {"effort": "low", "exclude": True} and seen[0][1] > 3000
    assert seen[1][0]["effort"] == "minimal"  # empty content -> retry with less reasoning


def test_daily_free_limit_stops_immediately(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda b, n: httpx.Response(429, json={"error": {
        "code": 429, "message": "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock more"}}))
    with pytest.raises(QuotaExhausted):
        ask(c)
    assert len(calls) == 1
