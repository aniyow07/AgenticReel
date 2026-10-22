"""The voices the app offers, per engine: Chatterbox-Turbo (Natural, local) and Edge TTS (Classic, online).
The engine defaults to TTS_ENGINE; each video can pick either."""
from __future__ import annotations

import re
import threading

from providers import tts

ACCENTS = {"US": "American", "GB": "British", "IN": "Indian", "AU": "Australian", "CA": "Canadian", "IE": "Irish",
           "NZ": "New Zealand", "ZA": "South African", "SG": "Singaporean", "PH": "Filipino", "KE": "Kenyan",
           "NG": "Nigerian", "TZ": "Tanzanian", "HK": "Hong Kong", "JP": "Japanese"}
# Voices from other languages that read English text with their own accent (word timings still work).
ACCENT_VOICES = ("ja-JP-",)

_cache: dict = {}


def voice_label(v: str) -> str:
    parts = v.replace("Neural", "").split("-")
    if len(parts) < 3:
        return v
    name = re.sub(r"(?<=[a-z])(Multilingual|Expressive)$", lambda m: f" ({m.group(1).lower()})", parts[-1])
    return f"{name} · {ACCENTS.get(parts[1], parts[1])} accent"


VOICE_ID = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]{2,40}Neural$")
_sample_lock = threading.Lock()


def _engine(engine: str | None) -> str:
    return engine if engine in ("chatterbox", "edge") else tts.engine()


def sample(voice: str, speed: int, engine: str | None = None):
    """A short spoken sample of a voice at a speed, made once and cached under outputs/."""
    from pathlib import Path

    from webapp.config import settings
    engine = _engine(engine)
    chatterbox = engine == "chatterbox"
    voice = voice or (settings().chatterbox_voice if chatterbox else settings().edge_voice)
    if not (tts.VOICE_ID if chatterbox else VOICE_ID).match(voice or ""):
        raise ValueError("Unknown voice.")
    known = {v["id"]: v for v in voices(engine)}
    if known and voice not in known:
        raise ValueError("Unknown voice.")
    speed = max(-30, min(40, int(speed)))
    out = settings().outputs_dir / "_voice_samples" / f"{'cb_' if chatterbox else ''}{voice}_{speed:+d}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        return out
    if chatterbox:
        name = known[voice]["label"].split(" · ")[0] if voice != tts.DEFAULT_VOICE else ""
        text = (f"Hi, I'm {name}. " if name else "Hi there! ") + "This is how your video will sound with my voice."
    else:
        name = voice_label(voice).split(" · ")[0].split(" (")[0]
        text = f"Hi, I'm {name}. This is how your video will sound with my voice."
    with _sample_lock:  # one recording at a time; a second click on the same voice reuses the first
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(out.stem + "_tmp.wav")
            if chatterbox:
                tts.ChatterboxTTS(voice=voice, rate=f"{speed:+d}%", timeout_s=120).synthesize(text, tmp)
            else:
                tts.EdgeTTS(voice=voice, rate=f"{speed:+d}%", timeout_s=30).synthesize(text, tmp)
            # the TTS stage works in WAV; a small MP3 is plenty for a preview
            import subprocess

            from rendering.media_utils import tool_path
            ff = tool_path("ffmpeg")
            done = False
            if ff:
                cp = subprocess.run([ff, "-v", "error", "-y", "-i", str(tmp), "-ac", "1", "-b:a", "64k", str(out)],
                                    capture_output=True, timeout=60)
                done = cp.returncode == 0 and out.exists()
            if done:
                Path(tmp).unlink(missing_ok=True)
            else:  # no ffmpeg: keep the WAV under the cached name; browsers sniff the format
                Path(tmp).replace(out)
    return out


def voices(engine: str | None = None) -> list[dict]:
    if _engine(engine) == "chatterbox":  # read each time: dropping a clip into assets/voices adds a voice
        rows = [{"id": v["id"], "label": v["label"], "gender": v["gender"], "accent": v.get("accent", "")}
                for v in tts.chatterbox_voices()]
        # the built-in voice first, then plain voices, then each accent together so the picker can group them
        return sorted(rows, key=lambda r: (r["id"] != tts.DEFAULT_VOICE, r["accent"], r["label"]))
    if "list" not in _cache:
        try:
            vs = tts.list_voices("en-", "edge") + [v for p in ACCENT_VOICES for v in tts.list_voices(p, "edge")]
            rows = [{"id": v["ShortName"], "label": voice_label(v["ShortName"]), "gender": v.get("Gender", ""),
                     "accent": ACCENTS.get(v["ShortName"].split("-")[1], v["ShortName"].split("-")[1])} for v in vs]
            rows.sort(key=lambda r: (r["accent"] != "American", r["accent"], r["label"]))
            _cache["list"] = rows
        except Exception:  # noqa: BLE001 - offline: the default voice still works
            _cache["list"] = []
    return _cache["list"]
