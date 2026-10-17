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
