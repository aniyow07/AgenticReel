"""Google Gemini (AI Studio API key) client with the same contract as OpenRouterClient.

Same rules as the OpenRouter client: models tried in order (GEMINI_MODEL then GEMINI_FALLBACK_MODELS),
JSON replies validated with the caller's Pydantic model and one bounded repair attempt, bounded backoff
with jitter for per-minute rate limits, no retries for daily quota / bad key, every call logged.
Uses the REST `models.generateContent` endpoint with the key in the `x-goog-api-key` header.
Free-tier calls are logged with cost 0 and basis "free_tier"; nothing is billed through this client.
"""
from __future__ import annotations

import random
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from core.config import Settings
from providers.openrouter import (AuthError, BudgetExceeded, LLMCall, LLMError, LLMUnavailable, QuotaExhausted,
                                  extract_json)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
THINKING_HEADROOM = 4000


class _Pacer:
    """Process-wide request pacing and per-model cooldowns (shared by every job and Streamlit thread)."""
    lock = threading.Lock()
    last_call = 0.0
    cooldown_until: dict[str, float] = {}   # model -> epoch seconds (per-minute limit hit)
    exhausted_until: dict[str, float] = {}  # model -> epoch seconds (daily quota used up)


class RateLimited(LLMError):
    def __init__(self, msg: str, wait_s: float, daily: bool):
        super().__init__(msg)
        self.wait_s, self.daily = wait_s, daily


def _next_pacific_midnight() -> float:
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return nxt.timestamp()


def parse_rate_limit(payload, headers) -> tuple[float | None, bool]:
    """(seconds to wait, is_daily_quota) from a 429 body: RetryInfo.retryDelay and QuotaFailure quotaId."""
    err = (payload or {}).get("error", {}) if isinstance(payload, dict) else {}
    wait, daily = None, False
    for d in err.get("details", []) or []:
        t = str(d.get("@type", ""))
        if t.endswith("RetryInfo") and d.get("retryDelay"):
            m = re.match(r"([\d.]+)s", str(d["retryDelay"]))
            wait = float(m.group(1)) if m else None
        if t.endswith("QuotaFailure"):
            for v in d.get("violations", []) or []:
                if re.search(r"per ?day|daily", str(v.get("quotaId", "")) + str(v.get("quotaMetric", "")), re.I):
                    daily = True
    msg = str(err.get("message", ""))
    if re.search(r"per ?day|perday|daily", msg, re.I):
        daily = True
    if wait is None:
        m = re.search(r"retry in ([\d.]+)\s*s", msg, re.I)
        wait = float(m.group(1)) if m else None
    if wait is None and headers is not None and headers.get("retry-after"):
        try:
            wait = float(headers["retry-after"])
        except ValueError:
            pass
    return wait, daily


class GeminiClient:
    provider = "gemini"

    def __init__(self, settings: Settings, logger=None, client: httpx.Client | None = None, sleep=time.sleep):
        self.s = settings
        self.log = logger
        self.http = client or httpx.Client(timeout=settings.llm_timeout_s)
        self.sleep = sleep
        self.job_cost = 0.0
        self.calls = 0
        self._no_thinking_cfg: set[str] = set()

    def models(self) -> list[str]:
        out = []
        for m in [self.s.gemini_model, *self.s.gemini_fallback_models]:
            if m and m not in out:
                out.append(m)
        return out

    def complete_json(self, *, stage: str, system: str, user: str, schema, prompt_version: str,
                      temperature: float = 0.6, max_tokens: int = 3000) -> LLMCall:
        if not self.s.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        errors = []
        for _round in range(2):
            now = time.time()
            usable = [m for m in self.models() if _Pacer.exhausted_until.get(m, 0) <= now]
            if not usable:
                raise QuotaExhausted("Gemini free-tier daily quota is used up for every configured model "
                                     "(resets at midnight Pacific)")
            ready = [m for m in usable if _Pacer.cooldown_until.get(m, 0) <= now]
            if not ready:  # everything is cooling down after a per-minute limit: wait for the soonest one
                wait = min(_Pacer.cooldown_until[m] for m in usable) - now
                if wait > self.s.gemini_max_wait_s:
                    raise LLMUnavailable(f"Gemini rate limited; next slot in {wait:.0f}s")
                self._log(stage, usable[0], prompt_version, "waiting", 0, 1, None,
                          note=f"all models cooling down; sleeping {wait:.0f}s")
                self.sleep(max(0.0, wait))
                ready = [min(usable, key=lambda m: _Pacer.cooldown_until.get(m, 0))]
            for model in ready:
                try:
                    return self._call_model(model, stage, system, user, schema, prompt_version, temperature,
                                            max_tokens)
                except (AuthError, BudgetExceeded):
                    raise
                except RateLimited as e:
                    # remember it for later calls instead of hammering this model every time
                    if e.daily:
                        _Pacer.exhausted_until[model] = _next_pacific_midnight()
                    else:
                        _Pacer.cooldown_until[model] = time.time() + e.wait_s
                    errors.append(f"{model}: {e}")
                except LLMError as e:
                    errors.append(f"{model}: {e}")
            if all(_Pacer.exhausted_until.get(m, 0) > time.time() for m in self.models()):
                raise QuotaExhausted("Gemini free-tier daily quota is used up for every configured model "
                                     "(resets at midnight Pacific)")
            if not any(_Pacer.cooldown_until.get(m, 0) > time.time() for m in self.models()):
                break
        raise LLMUnavailable("all configured Gemini models failed: " + " | ".join(errors))

    def _pace(self) -> None:
        """Keep at least GEMINI_MIN_INTERVAL_S between requests across the whole process."""
        with _Pacer.lock:
            gap = self.s.gemini_min_interval_s - (time.time() - _Pacer.last_call)
            if gap > 0:
                self.sleep(gap)
            _Pacer.last_call = time.time()

    def _body(self, model, system, contents, temperature, max_tokens, level):
        cfg = {"temperature": temperature, "maxOutputTokens": max_tokens + THINKING_HEADROOM,
               "responseMimeType": "application/json"}
        if model not in self._no_thinking_cfg:
            cfg["thinkingConfig"] = {"thinkingLevel": level}  # thinking tokens count toward maxOutputTokens
        return {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": cfg}

    def _call_model(self, model, stage, system, user, schema, prompt_version, temperature, max_tokens) -> LLMCall:
        contents = [{"role": "user", "parts": [{"text": user}]}]
        transient = repair = attempt = 0
        level = "low"
        while True:
            attempt += 1
            t0 = time.time()
            status, payload, err, headers = None, None, None, None
            self._pace()
            try:
                r = self.http.post(API.format(model=model), headers={"x-goog-api-key": self.s.gemini_api_key},
                                   json=self._body(model, system, contents, temperature, max_tokens, level),
                                   timeout=self.s.llm_timeout_s)
                status = r.status_code
                headers = r.headers
                try:
                    payload = r.json()
                except ValueError:
                    payload = None
            except httpx.TimeoutException as e:
                err = f"timeout: {e}"
            except httpx.HTTPError as e:
                err = f"network error: {e}"
            latency = time.time() - t0
            self.calls += 1
            if isinstance(payload, dict) and payload.get("error"):
                err = str(payload["error"].get("message", "error"))[:400]

            if status == 200 and payload and not err:
                usage_md = payload.get("usageMetadata") or {}
                usage = {"prompt_tokens": usage_md.get("promptTokenCount"),
                         "completion_tokens": usage_md.get("candidatesTokenCount"),
                         "reasoning_tokens": usage_md.get("thoughtsTokenCount"),
                         "total_tokens": usage_md.get("totalTokenCount")}
                cand = (payload.get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                used = payload.get("modelVersion", model)
                try:
                    data = schema.model_validate(extract_json(text))
                except (ValueError, ValidationError) as e:
                    self._log(stage, used, prompt_version, "invalid_output", latency, attempt, usage,
                              error=f"{str(e)[:400]} (finishReason={cand.get('finishReason')})")
                    if repair >= 1:
                        raise LLMError(f"invalid output after repair attempt: {str(e)[:200]}")
                    repair += 1
                    if not text.strip():
                        level = "minimal" if model != "gemini-3.8-flash" else "low"
                        continue
                    contents = contents + [
                        {"role": "model", "parts": [{"text": text[:4000]}]},
                        {"role": "user", "parts": [{"text": "That reply was not valid for the required JSON schema. "
                                                            f"Problem: {str(e)[:600]}\nReturn ONLY the corrected JSON."}]}]
                    continue
                self._log(stage, used, prompt_version, "ok", latency, attempt, usage)
                return LLMCall(used, data, usage, 0.0, "free_tier", latency, attempt)

            self._log(stage, model, prompt_version, "error", latency, attempt, None, error=err or f"HTTP {status}",
                      http_status=status)
            msg = (err or "").lower()
            if status == 400 and "thinking" in msg and model not in self._no_thinking_cfg:
                self._no_thinking_cfg.add(model)  # model does not accept thinkingConfig; retry without it
                continue
            if status in (401, 403) or "api key not valid" in msg:
                raise AuthError(f"Gemini rejected the API key (HTTP {status})")
            if status == 429:
                wait, daily = parse_rate_limit(payload, headers)
                if daily:
                    raise RateLimited(f"{model}: daily free-tier quota used up", 0, True)
                wait = max(wait or 0, 2 ** (transient + 2))  # at least 4s, 8s, 16s...
                if wait <= self.s.gemini_retry_wait_s and transient < self.s.llm_max_retries:
                    transient += 1
                    self._log(stage, model, prompt_version, "waiting", 0, attempt, None,
                              note=f"per-minute limit; waiting {wait:.0f}s before retrying")
                    self.sleep(wait)
                    continue
                raise RateLimited(f"{model}: per-minute limit (retry in {wait:.0f}s)", wait, False)
            if status in (400, 404):
                raise LLMError(f"model rejected the request (HTTP {status}): {err}")
            if transient >= self.s.llm_max_retries:
                raise LLMError(f"gave up after {transient + 1} attempts: {err or status}")
            transient += 1
            m = re.search(r"retry in ([\d.]+)s", msg) or re.search(r'"retrydelay":\s*"(\d+)', str(payload).lower())
            delay = float(m.group(1)) if m else (2 ** transient) + random.uniform(0, 1)
            self.sleep(min(delay, 60.0))

    def _log(self, stage, model, prompt_version, status, latency, attempt, usage, **extra):
        if not self.log:
            return
        self.log.log(stage, "gemini", status, provider="gemini", model=model, prompt_version=prompt_version,
                     latency_s=round(latency, 3), retry_count=attempt - 1, usage=usage or {}, cost=0.0,
                     cost_basis="free_tier", **extra)
        self.log.cost(stage, "gemini", model, usage, 0.0, "free_tier", status)
