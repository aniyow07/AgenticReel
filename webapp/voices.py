"""The Edge TTS voices the app offers, labelled and grouped by accent."""
from __future__ import annotations

import re

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
_sample_lock = __import__("threading").Lock()


def sample(voice: str, speed: int):
    """A short spoken sample of a voice at a speed, made once with Edge TTS and cached under outputs/."""
    from pathlib import Path

    from webapp.config import settings
    if not VOICE_ID.match(voice or ""):
        raise ValueError("Unknown voice.")
    known = {v["id"] for v in voices()}
    if known and voice not in known:
        raise ValueError("Unknown voice.")
    speed = max(-30, min(40, int(speed)))
    out = settings().outputs_dir / "_voice_samples" / f"{voice}_{speed:+d}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        return out
    name = voice_label(voice).split(" · ")[0].split(" (")[0]
    text = f"Hi, I'm {name}. This is how your video will sound with my voice."
    with _sample_lock:  # one recording at a time; a second click on the same voice reuses the first
        if not out.exists():
            from providers.tts import EdgeTTS
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(out.stem + "_tmp.wav")
            EdgeTTS(voice=voice, rate=f"{speed:+d}%", timeout_s=30).synthesize(text, tmp)
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


def voices() -> list[dict]:
    if "list" not in _cache:
        try:
            from providers.tts import list_voices
            vs = list_voices("en-") + [v for p in ACCENT_VOICES for v in list_voices(p)]
            rows = [{"id": v["ShortName"], "label": voice_label(v["ShortName"]), "gender": v.get("Gender", ""),
                     "accent": ACCENTS.get(v["ShortName"].split("-")[1], v["ShortName"].split("-")[1])} for v in vs]
            rows.sort(key=lambda r: (r["accent"] != "American", r["accent"], r["label"]))
            _cache["list"] = rows
        except Exception:  # noqa: BLE001 - offline: the default voice still works
            _cache["list"] = []
    return _cache["list"]
