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
            "exec_mode": s.execution_mode, "online_research": s.online_research,
            "default_voice": s.tts_voice, "tts_engine": "edge" if s.tts_provider in ("edge", "sapi") else "chatterbox",
            "default_voices": {"chatterbox": s.chatterbox_voice, "edge": s.edge_voice}, "ready": ready, "gpu": s.gpu, "gpu_found": gpu_found(),
            "asset_version": asset_version()}


def gpu_found() -> bool:
    """Whether this computer has a working NVIDIA encoder (checked once, then cached)."""
    from rendering import gpu
    return gpu.available()


def asset_version() -> str:
    """Changes whenever a preview clip in assets/ui is replaced, so browsers fetch the new file instead of a
    cached old one (the clips are served with a long cache lifetime)."""
    from webapp.config import UI_ASSETS
    stamps = [int(p.stat().st_mtime) for p in UI_ASSETS.glob("preview_*.mp4")]
    return str(max(stamps)) if stamps else "0"
