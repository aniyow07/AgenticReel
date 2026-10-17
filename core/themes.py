"""Colour palettes. OG videos pick one per video (seeded by the job seed and topic) so consecutive reels
look different; Manim clips receive the same palette so diagrams match the video around them."""
from __future__ import annotations

import hashlib
import re

PALETTES: list[dict] = [
    {"name": "midnight", "background": "#0B1020", "surface": "#151C33", "primary": "#7C9CFF", "accent": "#FFB547",
     "text": "#F5F7FF", "mutedText": "#A9B2D0"},
    {"name": "ocean", "background": "#04161F", "surface": "#0B2A38", "primary": "#2EC4FF", "accent": "#7CFFCB",
     "text": "#F0FBFF", "mutedText": "#9CC7D6"},
    {"name": "sunset", "background": "#1A0B1E", "surface": "#2C1433", "primary": "#FF6B9A", "accent": "#FFC75F",
     "text": "#FFF5F8", "mutedText": "#D3A9C0"},
    {"name": "forest", "background": "#0A1710", "surface": "#13281C", "primary": "#5BE38B", "accent": "#F4E36B",
     "text": "#F2FFF6", "mutedText": "#A6CDB3"},
    {"name": "violet", "background": "#120B24", "surface": "#1E1440", "primary": "#A47CFF", "accent": "#4FF2E3",
     "text": "#F7F3FF", "mutedText": "#B9ACD9"},
    {"name": "ember", "background": "#170C08", "surface": "#2B1810", "primary": "#FF8A3D", "accent": "#FFD84D",
     "text": "#FFF7F0", "mutedText": "#D7B6A0"},
]
FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def pick_palette(seed: int, topic: str, name: str | None = None) -> dict:
    if name:
        for p in PALETTES:
            if p["name"] == name:
                return {**p, "fontFamily": FONT}
    h = int(hashlib.sha256(f"{seed}:{topic}".encode()).hexdigest(), 16)
    return {**PALETTES[h % len(PALETTES)], "fontFamily": FONT}


def manim_palette(theme: dict) -> dict:
    return {k: theme[k] for k in ("background", "surface", "primary", "accent", "text", "mutedText")
            if _HEX.match(str(theme.get(k, "")))}
