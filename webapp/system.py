"""What the header shows: the AI provider and model, and which styles have gameplay footage."""
from __future__ import annotations

from webapp.config import settings


def info() -> dict:
    s = settings()
    from core.gameplay import library_status
    if s.llm_provider == "gemini":
        provider, model, key = "Gemini", s.gemini_model, bool(s.gemini_api_key)
    else:
        provider, model, key = "OpenRouter", s.openrouter_model, bool(s.openrouter_api_key)
    ready = {"og": True}
    try:
        for game, clips in library_status(deep=False).items():
            ready[game] = any(c.usable for c in clips)
    except Exception:  # noqa: BLE001
        pass
    return {"provider": provider, "model": model.split("/")[-1].split(":")[0], "has_key": key,
            "exec_mode": s.execution_mode, "default_voice": s.tts_voice, "ready": ready}
