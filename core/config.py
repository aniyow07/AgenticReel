"""Runtime configuration read from environment variables (and an optional .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # python-dotenv is optional
    pass

ExecutionMode = Literal["AI_PREFERRED", "LOCAL_ONLY", "AI_REQUIRED"]


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _float(v: str | None, default: float) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


@dataclass
class Settings:
    llm_provider: str = "openrouter"  # "openrouter" | "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_models: list[str] = field(default_factory=lambda: ["gemini-3.5-flash-lite"])
    gemini_min_interval_s: float = 6.0   # minimum gap between Gemini requests (6s = at most 10 per minute)
    gemini_retry_wait_s: float = 20.0    # wait this long at most for a per-minute limit before switching model
    gemini_max_wait_s: float = 90.0      # if every model is cooling down, wait at most this long
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_fallback_models: list[str] = field(default_factory=list)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    allow_paid_models: bool = False
    max_api_spend_usd: float = 5.0
    execution_mode: ExecutionMode = "AI_PREFERRED"
    llm_timeout_s: float = 90
    llm_max_retries: int = 2
    tts_provider: str = "chatterbox"
    tts_voice: str = "default"
    chatterbox_voice: str = "default"     # default voice when a video picks the Natural (Chatterbox) engine
    edge_voice: str = "en-US-AriaNeural"  # default voice when a video picks the Classic (Edge) engine
    tts_rate: str = "+10%"
    max_repair_attempts: int = 2
    max_output_mb: float = 100
    max_upload_mb: float = 50
    online_research: bool = False
    gpu: str = "auto"  # "auto" | "on" | "off": NVENC encoding and Remotion's GPU backend (rendering/gpu.py)
    outputs_dir: Path = ROOT / "outputs"
    remotion_dir: Path = ROOT / "remotion"
    assets_dir: Path = ROOT / "assets"

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        mode = (e("AGENTREEL_EXECUTION_MODE") or "AI_PREFERRED").upper()
        if mode not in ("AI_PREFERRED", "LOCAL_ONLY", "AI_REQUIRED"):
            mode = "AI_PREFERRED"
        provider = (e("LLM_PROVIDER") or "openrouter").strip().lower()
        tts_engine = (e("TTS_ENGINE") or "chatterbox").strip().lower()
        return cls(
            llm_provider=provider if provider in ("openrouter", "gemini") else "openrouter",
            gemini_api_key=(e("GEMINI_API_KEY") or "").strip(),
            gemini_model=(e("GEMINI_MODEL") or "gemini-3.8-flash").strip(),
            gemini_min_interval_s=_float(e("GEMINI_MIN_INTERVAL_S"), 6.0),
            gemini_retry_wait_s=_float(e("GEMINI_RETRY_WAIT_S"), 20.0),
            gemini_max_wait_s=_float(e("GEMINI_MAX_WAIT_S"), 90.0),
            gemini_fallback_models=[m.strip() for m in (e("GEMINI_FALLBACK_MODELS") or "gemini-3.5-flash-lite").split(",")
                                    if m.strip()],
            openrouter_api_key=(e("OPENROUTER_API_KEY") or "").strip(),
            openrouter_model=(e("OPENROUTER_MODEL") or "openrouter/free").strip(),
            openrouter_fallback_models=[m.strip() for m in (e("OPENROUTER_FALLBACK_MODELS") or "").split(",")
                                        if m.strip()],
            allow_paid_models=_bool(e("ALLOW_PAID_MODELS"), False),
            max_api_spend_usd=_float(e("MAX_API_SPEND_USD"), 5.0),
            execution_mode=mode,  # type: ignore[arg-type]
            llm_timeout_s=_float(e("OPENROUTER_TIMEOUT_S"), 90),
            # TTS_ENGINE=chatterbox (local, default) or edge (the old online voices: TTS_PROVIDER/TTS_VOICE apply)
            tts_provider=("chatterbox" if tts_engine == "chatterbox" else (e("TTS_PROVIDER") or "edge").strip().lower()),
            tts_voice=((e("CHATTERBOX_VOICE") or "default") if tts_engine == "chatterbox"
                       else (e("TTS_VOICE") or "en-US-AriaNeural")).strip(),
            chatterbox_voice=(e("CHATTERBOX_VOICE") or "default").strip(),
            edge_voice=(e("TTS_VOICE") or "en-US-AriaNeural").strip(),
            tts_rate=(e("TTS_RATE") or "+10%").strip(),
            max_repair_attempts=int(_float(e("MAX_REPAIR_ATTEMPTS"), 2)),
            max_output_mb=_float(e("MAX_OUTPUT_MB"), 100),
            online_research=_bool(e("ONLINE_RESEARCH"), False),
            gpu=g if (g := (e("AGENTREEL_GPU") or "auto").strip().lower()) in ("auto", "on", "off") else "auto",
            outputs_dir=Path(e("AGENTREEL_OUTPUT_DIR") or ROOT / "outputs"),
        )

    def public_dict(self) -> dict:
        """Settings safe to persist: the API key is never included."""
        d = {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items()}
        d["openrouter_api_key"] = "set" if self.openrouter_api_key else "unset"
        d["gemini_api_key"] = "set" if self.gemini_api_key else "unset"
        return d
