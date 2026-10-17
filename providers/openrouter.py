"""OpenRouter chat client with bounded retries, model fallback and spend control.

Policy:
  * Models are tried in order: OPENROUTER_MODEL, then OPENROUTER_FALLBACK_MODELS.
  * A model is skipped unless it is free, or ALLOW_PAID_MODELS=true. Pricing comes from
    OpenRouter's /models list; a model whose price cannot be confirmed is treated as paid.
  * 429 / 5xx / timeouts / network errors: bounded exponential backoff with jitter, then next model.
  * 400/404 (bad model id or request): next model immediately. 401: stop (bad key).
    402 (credits exhausted): stop; it is never retried.
  * Every response is parsed as JSON and validated with the caller's Pydantic model; a malformed
    reply gets one bounded repair attempt per model.
  * Cost: usage.cost from the response when supplied ("measured"), otherwise estimated from
    pricing ("estimated"), otherwise "unknown". A global ledger enforces MAX_API_SPEND_USD.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from core.config import Settings

T = TypeVar("T", bound=BaseModel)

FREE_ROUTER_IDS = {"openrouter/free"}
REASONING_HEADROOM = 6000
MODELS_CACHE_TTL_S = 6 * 3600


class LLMError(RuntimeError):
    pass


class LLMUnavailable(LLMError):
    """No configured model could produce a valid answer."""


class BudgetExceeded(LLMError):
    pass


class AuthError(LLMError):
    pass


class QuotaExhausted(LLMError):
    pass


@dataclass
class LLMCall:
    model: str
    data: BaseModel
    usage: dict
    cost: float | None
    cost_basis: str
    latency_s: float
    attempts: int


class SpendLedger:
    """Cumulative spend across all jobs, stored next to the outputs."""

    _lock = threading.Lock()

    def __init__(self, path: Path):
        self.path = path

    def total(self) -> float:
        try:
            return float(json.loads(self.path.read_text(encoding="utf-8")).get("total_usd", 0.0))
        except (OSError, ValueError):
            return 0.0

    def add(self, usd: float) -> float:
        with self._lock:
            total = self.total() + max(0.0, usd)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"total_usd": round(total, 6), "updated": time.time()}),
                                 encoding="utf-8")
            return total


def extract_json(text: str):
    """Parse JSON from a model reply, tolerating ```json fences and leading prose."""
    if text is None:
        raise ValueError("empty reply")
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object found in reply")
    start = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    return json.loads(t[start:end + 1])


class OpenRouterClient:
    def __init__(self, settings: Settings, logger=None, client: httpx.Client | None = None,
                 sleep=time.sleep, ledger: SpendLedger | None = None):
        self.s = settings
        self.log = logger
        self.http = client or httpx.Client(timeout=settings.llm_timeout_s)
        self.sleep = sleep
        self.ledger = ledger or SpendLedger(settings.outputs_dir / ".spend_ledger.json")
        self._models: dict[str, dict] | None = None
        self.job_cost = 0.0
        self.calls = 0

    # ---------- model catalogue ----------
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.s.openrouter_api_key}", "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost", "X-Title": "AgentReel"}

    def catalogue(self) -> dict[str, dict]:
        if self._models is not None:
            return self._models
        cache = self.s.outputs_dir / ".openrouter_models.json"
        try:
            if cache.exists() and time.time() - cache.stat().st_mtime < MODELS_CACHE_TTL_S:
                self._models = json.loads(cache.read_text(encoding="utf-8"))
                return self._models
        except (OSError, ValueError):
            pass
        try:
            r = self.http.get(f"{self.s.openrouter_base_url}/models", timeout=30)
            r.raise_for_status()
            self._models = {m["id"]: {"pricing": m.get("pricing", {}),
                                      "supported_parameters": m.get("supported_parameters", [])}
                            for m in r.json().get("data", [])}
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(self._models), encoding="utf-8")
        except (httpx.HTTPError, ValueError, KeyError):
            self._models = {}
        return self._models

    def is_free(self, model: str) -> bool:
        if model in FREE_ROUTER_IDS:
            return True
        info = self.catalogue().get(model)
        if not info:
            return False  # unknown price -> treat as paid
        p = info.get("pricing", {})
        try:
            return float(p.get("prompt", 1)) == 0 and float(p.get("completion", 1)) == 0
        except (TypeError, ValueError):
            return False

    def supports(self, model: str, param: str) -> bool:
        if model in FREE_ROUTER_IDS:
            return True
        return param in self.catalogue().get(model, {}).get("supported_parameters", [])

    def supports_json(self, model: str) -> bool:
        if model in FREE_ROUTER_IDS:
            return True
        sp = self.catalogue().get(model, {}).get("supported_parameters", [])
        return "response_format" in sp or "structured_outputs" in sp

    def candidate_models(self) -> tuple[list[str], list[str]]:
        allowed, skipped = [], []
        for m in [self.s.openrouter_model, *self.s.openrouter_fallback_models]:
            if not m or m in allowed:
                continue
            if self.s.allow_paid_models or self.is_free(m):
                allowed.append(m)
            else:
                skipped.append(m)
        return allowed, skipped

    def _estimate(self, model: str, usage: dict) -> float | None:
        p = self.catalogue().get(model, {}).get("pricing")
        if not p or not usage:
            return None
        try:
            return float(p.get("prompt", 0)) * usage.get("prompt_tokens", 0) + \
                float(p.get("completion", 0)) * usage.get("completion_tokens", 0)
        except (TypeError, ValueError):
            return None

    # ---------- main entry ----------
    def complete_json(self, *, stage: str, system: str, user: str, schema: type[T], prompt_version: str,
                      temperature: float = 0.6, max_tokens: int = 3000) -> LLMCall:
        if not self.s.openrouter_api_key:
            raise LLMUnavailable("OPENROUTER_API_KEY is not set")
        models, skipped = self.candidate_models()
        if skipped and self.log:
            self.log.log(stage, "openrouter", "skipped_models", skipped=skipped,
                         reason="paid or unknown-price models are disabled (ALLOW_PAID_MODELS=false)")
        if not models:
            raise LLMUnavailable("no free model is configured and paid models are disabled")
        errors: list[str] = []
        for model in models:
            try:
                return self._call_model(model, stage, system, user, schema, prompt_version, temperature,
                                        max_tokens)
            except (AuthError, QuotaExhausted, BudgetExceeded):
                raise
            except LLMError as e:
                errors.append(f"{model}: {e}")
        raise LLMUnavailable("all configured models failed: " + " | ".join(errors))

    def _check_budget(self) -> None:
        spent = self.ledger.total()
        if spent >= self.s.max_api_spend_usd:
            raise BudgetExceeded(f"spend ceiling reached (${spent:.4f} of ${self.s.max_api_spend_usd:.2f})")

    def _call_model(self, model, stage, system, user, schema, prompt_version, temperature, max_tokens) -> LLMCall:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        transient_tries = 0
        repair_tries = 0
        attempt = 0
        effort = "low"
        while True:
            attempt += 1
            self._check_budget()
            body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            if self.supports_json(model):
                body["response_format"] = {"type": "json_object"}
            if self.supports(model, "reasoning"):
                # Reasoning tokens count against max_tokens; keep reasoning short and hidden and leave
                # room for the JSON answer, otherwise free reasoning models return empty content.
                body["reasoning"] = {"effort": effort, "exclude": True}
                body["max_tokens"] = min(max_tokens + REASONING_HEADROOM, 16000)
            t0 = time.time()
            status, payload, err, headers = None, None, None, {}
            try:
                r = self.http.post(f"{self.s.openrouter_base_url}/chat/completions", headers=self._headers(),
                                   json=body, timeout=self.s.llm_timeout_s)
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

            # Errors can come as HTTP status or as an error object inside a 200 body.
            if status is not None and payload and isinstance(payload, dict) and payload.get("error"):
                code = payload["error"].get("code")
                if isinstance(code, int) and status == 200:
                    status = code
                err = str(payload["error"].get("message", "provider error"))[:300]
                meta = payload["error"].get("metadata") or {}
                detail = meta.get("raw") or meta.get("provider_name")
                if detail:
                    err += f" ({str(detail)[:200]})"

            if status == 200 and payload and not err:
                usage = payload.get("usage") or {}
                cost = usage.get("cost")
                basis = "measured" if cost is not None else "estimated"
                if cost is None:
                    cost = self._estimate(model, usage)
                    if cost is None:
                        basis = "unknown"
                used_model = payload.get("model", model)
                if cost:
                    self.ledger.add(float(cost))
                    self.job_cost += float(cost)
                content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
                try:
                    data = schema.model_validate(extract_json(content))
                except (ValueError, ValidationError) as e:
                    self._log(stage, used_model, prompt_version, "invalid_output", latency, attempt, usage, cost,
                              basis, error=str(e)[:500])
                    if repair_tries >= 1:
                        raise LLMError(f"invalid output after repair attempt: {str(e)[:200]}")
                    repair_tries += 1
                    if not (content or "").strip():
                        # usually reasoning ate the budget: retry once with minimal reasoning, same prompt
                        effort = "minimal"
                        continue
                    messages = messages + [
                        {"role": "assistant", "content": (content or "")[:4000]},
                        {"role": "user", "content": "That reply was not valid for the required JSON schema. "
                                                    f"Problem: {str(e)[:600]}\nReturn ONLY the corrected JSON."}]
                    continue
                self._log(stage, used_model, prompt_version, "ok", latency, attempt, usage, cost, basis)
                return LLMCall(used_model, data, usage, cost, basis, latency, attempt)

            self._log(stage, model, prompt_version, "error", latency, attempt, None, None, "unknown",
                      error=err or f"HTTP {status}", http_status=status)
            if status == 401:
                raise AuthError("OpenRouter rejected the API key (401)")
            if status == 429 and re.search(r"per[- ]?day|daily", (err or "").lower()):
                raise QuotaExhausted(f"OpenRouter daily free-model limit reached: {err}")
            if status == 402:
                raise QuotaExhausted("OpenRouter reports insufficient credits or quota (402); not retrying")
            if status in (400, 404, 403):
                raise LLMError(f"model rejected the request (HTTP {status}): {err}")
            # transient: 408, 429, 5xx, timeouts, network errors
            if transient_tries >= self.s.llm_max_retries:
                raise LLMError(f"gave up after {transient_tries + 1} attempts: {err or status}")
            transient_tries += 1
            retry_after = headers.get("retry-after") if status == 429 else None
            try:
                retry_after = float(retry_after) if retry_after else None
            except ValueError:
                retry_after = None
            delay = min(30.0, (2 ** transient_tries) + random.uniform(0, 1))
            if retry_after:
                delay = min(60.0, retry_after)
            self.sleep(delay)

    def _log(self, stage, model, prompt_version, status, latency, attempt, usage, cost, basis, **extra):
        if not self.log:
            return
        self.log.log(stage, "openrouter", status, provider="openrouter", model=model, prompt_version=prompt_version,
                     latency_s=round(latency, 3), retry_count=attempt - 1, usage=usage or {}, cost=cost,
                     cost_basis=basis, **extra)
        self.log.cost(stage, "openrouter", model, usage, cost, basis, status)

