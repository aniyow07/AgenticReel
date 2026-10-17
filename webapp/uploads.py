"""Saving documents attached in the browser to outputs/_uploads."""
from __future__ import annotations

import secrets
from pathlib import Path

from webapp.config import AUDIO_EXT, MAX_UPLOAD, SOURCE_EXT, settings


def save_upload(name: str, body: bytes) -> dict:
    from core.jobs import safe_filename
    ext = Path(name).suffix.lower()
    if ext not in SOURCE_EXT | AUDIO_EXT:
        raise ValueError(f"{name}: use a PDF, DOCX, TXT or MD file")
    if len(body) > MAX_UPLOAD:
        raise ValueError(f"{name} is larger than 50 MB")
    d = settings().outputs_dir / "_uploads" / secrets.token_hex(6)
    d.mkdir(parents=True, exist_ok=True)
    p = d / safe_filename(name)
    p.write_bytes(body)
    pages = None
    if ext == ".pdf":
        try:
            import fitz
            with fitz.open(p) as doc:
                pages = doc.page_count
        except Exception:  # noqa: BLE001
            pages = None
    return {"path": str(p), "name": Path(name).name, "pages": pages, "size": len(body)}
