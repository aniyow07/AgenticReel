"""Gemini client behaviour with a mocked HTTP transport (no real API calls)."""
import json

import httpx
import pytest
from pydantic import BaseModel

from core.runlog import RunLogger
from providers.gemini import GeminiClient, _Pacer


@pytest.fixture(autouse=True)
def reset_pacer():
    _Pacer.cooldown_until.clear()
    _Pacer.exhausted_until.clear()
    _Pacer.last_call = 0.0
    yield
from providers.openrouter import AuthError, LLMUnavailable, QuotaExhausted


class Answer(BaseModel):
    answer: str


def reply(text, model="gemini-3.8-flash"):
    return httpx.Response(200, json={"modelVersion": model, "candidates": [
        {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 7,
                          "totalTokenCount": 22}})


def make(settings, tmp_path, handler, fallbacks=("gemini-3.5-flash-lite",)):
    settings.gemini_api_key = "g-test-key"
    settings.gemini_model = "gemini-3.8-flash"
    settings.gemini_fallback_models = list(fallbacks)
    calls = []

    def route(req: httpx.Request):
        assert req.headers["x-goog-api-key"] == "g-test-key"
        body = json.loads(req.content)
        model = req.url.path.split("/models/")[1].split(":")[0]
        calls.append((model, body))
        return handler(model, body, len(calls))
    log = RunLogger("j", tmp_path / "logs")
    return GeminiClient(settings, logger=log, client=httpx.Client(transport=httpx.MockTransport(route)),
                        sleep=lambda s: None), calls, log


def ask(c):
    return c.complete_json(stage="t", system="sys", user="u", schema=Answer, prompt_version="v")


def test_json_reply_and_request_shape(settings, tmp_path):
    c, calls, log = make(settings, tmp_path, lambda m, b, n: reply('{"answer": "hi"}'))
    r = ask(c)
    assert r.data.answer == "hi" and r.cost == 0.0 and r.cost_basis == "free_tier"
    body = calls[0][1]
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "g-test-key" not in log.run_log.read_text()


def test_per_minute_429_retries_then_falls_back(settings, tmp_path):
    def h(model, body, n):
        if model == "gemini-3.8-flash":
            return httpx.Response(429, json={"error": {"code": 429, "message": "Quota exceeded per minute. "
                                                                               "Please retry in 2.5s."}})
        return reply('{"answer": "lite"}', model)
    settings.llm_max_retries = 2
    c, calls, _ = make(settings, tmp_path, h)
    assert ask(c).data.answer == "lite"
    assert [m for m, _ in calls].count("gemini-3.8-flash") == 3


def test_daily_quota_and_bad_key_stop_immediately(settings, tmp_path):
    c, calls, _ = make(settings, tmp_path, lambda m, b, n: httpx.Response(
        429, json={"error": {"message": "Quota exceeded for metric generate_content_free_tier_requests, "
                                        "limit PerDay"}}))
    with pytest.raises(QuotaExhausted):
        ask(c)
    assert len(calls) == 2  # each model asked once (daily quotas are per model), never retried
    with pytest.raises(QuotaExhausted):
        ask(c)  # remembered: no further requests until the quota resets
    assert len(calls) == 2
    _Pacer.exhausted_until.clear()
    c, calls, _ = make(settings, tmp_path, lambda m, b, n: httpx.Response(
        400, json={"error": {"message": "API key not valid. Please pass a valid API key."}}))
    with pytest.raises(AuthError):
        ask(c)


def test_unsupported_thinking_config_is_dropped(settings, tmp_path):
    def h(model, body, n):
        if "thinkingConfig" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "thinking_level is not supported for this model"}})
        return reply('{"answer": "ok"}')
    c, calls, _ = make(settings, tmp_path, h, fallbacks=())
    assert ask(c).data.answer == "ok" and len(calls) == 2


def test_invalid_json_repaired_once_then_rejected(settings, tmp_path):
    replies = iter(['not json', '{"answer": "fixed"}'])
    c, _, _ = make(settings, tmp_path, lambda m, b, n: reply(next(replies)), fallbacks=())
    assert ask(c).data.answer == "fixed"
    c, calls, _ = make(settings, tmp_path, lambda m, b, n: reply('{"wrong": 1}'), fallbacks=())
    with pytest.raises(LLMUnavailable):
        ask(c)
    assert len(calls) == 2


def test_provider_selection(settings, tmp_path):
    from core.jobs import Job
    from orchestrator import make_llm
    from providers.openrouter import OpenRouterClient
    job = Job(tmp_path / "outputs", "sel")
    settings.llm_provider, settings.gemini_api_key = "gemini", "k"
    assert isinstance(make_llm(settings, job), GeminiClient)
    settings.llm_provider, settings.openrouter_api_key = "openrouter", "k2"
    assert isinstance(make_llm(settings, job), OpenRouterClient)
    settings.llm_provider, settings.gemini_api_key = "gemini", ""
    assert make_llm(settings, job) is None  # AI_PREFERRED without a key -> local fallback


def test_cooldown_skips_rate_limited_model_on_later_calls(settings, tmp_path):
    waits = []

    def h(model, body, n):
        if model == "gemini-3.8-flash":
            return httpx.Response(429, json={"error": {"code": 429, "message": "Resource exhausted", "details": [
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "45s"}]}})
        return reply('{"answer": "lite"}', model)
    c, calls, _ = make(settings, tmp_path, h)
    c.sleep = waits.append
    assert ask(c).data.answer == "lite"
    assert ask(c).data.answer == "lite"
    primary = [m for m, _ in calls if m == "gemini-3.8-flash"]
    assert len(primary) == 1  # 45s > retry budget: switched model and did not retry the primary on the 2nd call


def test_requests_are_spaced(settings, tmp_path):
    waits = []
    settings.gemini_min_interval_s = 6
    c, _, _ = make(settings, tmp_path, lambda m, b, n: reply('{"answer": "x"}'), fallbacks=())
    c.sleep = waits.append
    ask(c)
    ask(c)
    assert waits and 5 < waits[-1] <= 6