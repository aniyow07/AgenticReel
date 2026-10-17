"""Text-to-speech providers.

Each provider writes one audio file per narration chunk and returns the
*measured* duration (ffprobe), plus word timings when the engine reports them.
A failed or empty synthesis raises TTSError; nothing is silently substituted.

Providers:
  edge   - Microsoft Edge online voices via edge-tts (word boundaries available)
  sapi   - offline Windows SAPI voices via pyttsx3 (no word timings)
  supplied - user-provided narration audio (one file for the whole script)
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from rendering.media_utils import MediaError, probe, require_tool, run


class TTSError(RuntimeError):
    pass


@dataclass
class TTSResult:
    path: Path
    duration_s: float
    provider: str
    voice: str
    word_timings: list[tuple[str, float, float]] = field(default_factory=list)
    elapsed_s: float = 0.0


def _to_wav(src: Path, dst: Path) -> None:
    """Normalise every chunk to 48 kHz stereo PCM so chunks can be concatenated exactly."""
    cp = run([require_tool("ffmpeg"), "-v", "error", "-y", "-i", str(src), "-ar", "48000", "-ac", "2",
              "-c:a", "pcm_s16le", str(dst)], timeout=120)
    if cp.returncode != 0:
        raise TTSError(f"could not convert TTS audio: {cp.stderr[:300]}")


def _measure(path: Path) -> float:
    try:
        info = probe(path)
    except MediaError as e:
        raise TTSError(f"TTS produced an unreadable file: {e}") from e
    if not info.has_audio or info.duration < 0.15:
        raise TTSError("TTS produced no usable audio")
    return info.duration


class EdgeTTS:
    name = "edge"

    def __init__(self, voice: str = "en-US-AriaNeural", rate: str = "+0%", timeout_s: float = 60):
        self.voice, self.rate, self.timeout_s = voice, rate, timeout_s

    @staticmethod
    def available() -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    async def _synth(self, text: str, mp3: Path) -> list[tuple[str, float, float]]:
        import edge_tts

        comm = edge_tts.Communicate(text, self.voice, rate=self.rate, boundary="WordBoundary")
        words = []
        with open(mp3, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    s = chunk["offset"] / 1e7
                    words.append((chunk["text"], s, s + chunk["duration"] / 1e7))
        return words

    def synthesize(self, text: str, out_wav: Path) -> TTSResult:
        t0 = time.time()
        mp3 = out_wav.with_suffix(".mp3")
        result: dict = {}

        def runner():  # edge-tts is async; run it in its own loop so this works inside Streamlit too
            try:
                result["words"] = asyncio.run(asyncio.wait_for(self._synth(text, mp3), self.timeout_s))
            except BaseException as e:  # noqa: BLE001
                result["error"] = e

        th = threading.Thread(target=runner, daemon=True)
        th.start()
        th.join(self.timeout_s + 5)
        if th.is_alive() or "error" in result:
            err = result.get("error", "timed out")
            raise TTSError(f"Edge TTS failed: {type(err).__name__ if not isinstance(err, str) else ''} {err}")
        if not mp3.exists() or mp3.stat().st_size == 0:
            raise TTSError("Edge TTS returned no audio")
        _to_wav(mp3, out_wav)
        mp3.unlink(missing_ok=True)
        dur = _measure(out_wav)
        return TTSResult(out_wav, dur, self.name, self.voice, result.get("words", []), time.time() - t0)


class SapiTTS:
    """Offline fallback using the voices installed in Windows (pyttsx3 / SAPI5)."""

    name = "sapi"

    def __init__(self, voice: str = "", rate_wpm: int = 175):
        self.voice, self.rate_wpm = voice, rate_wpm

    @staticmethod
    def available() -> bool:
        try:
            import pyttsx3

            eng = pyttsx3.init()
            ok = bool(eng.getProperty("voices"))
            eng.stop()
            return ok
        except Exception:  # noqa: BLE001
            return False

    def synthesize(self, text: str, out_wav: Path) -> TTSResult:
        import pyttsx3

        t0 = time.time()
        raw = out_wav.with_name(out_wav.stem + "_raw.wav")
        eng = pyttsx3.init()
        eng.setProperty("rate", self.rate_wpm)
        if self.voice:
            for v in eng.getProperty("voices"):
                if self.voice.lower() in (v.name or "").lower() or self.voice == v.id:
                    eng.setProperty("voice", v.id)
                    break
        eng.save_to_file(text, str(raw))
        eng.runAndWait()
        eng.stop()
        if not raw.exists() or raw.stat().st_size < 1000:
            raise TTSError("SAPI TTS produced no audio")
        _to_wav(raw, out_wav)
        raw.unlink(missing_ok=True)
        return TTSResult(out_wav, _measure(out_wav), self.name, self.voice or "default", [], time.time() - t0)


def get_provider(name: str, voice: str, rate: str):
    if name == "edge":
        return EdgeTTS(voice=voice, rate=rate)
    if name == "sapi":
        return SapiTTS()
    raise TTSError(f"unknown TTS provider {name!r}")


def provider_chain(preferred: str, voice: str, rate: str, local_only: bool) -> list:
    """Preferred provider first, then the offline SAPI fallback. Edge needs the network, so LOCAL_ONLY
    still allows it only if explicitly preferred (it is TTS, not an LLM call)."""
    chain = []
    if preferred == "edge" and EdgeTTS.available():
        chain.append(EdgeTTS(voice=voice, rate=rate))
    if preferred in ("edge", "sapi") and SapiTTS.available():
        chain.append(SapiTTS())
    return chain


def prepare_supplied_audio(src: Path, out_wav: Path) -> TTSResult:
    if not src.is_file():
        raise TTSError(f"narration audio not found: {src}")
    _to_wav(src, out_wav)
    return TTSResult(out_wav, _measure(out_wav), "supplied", "user", [], 0.0)


FALLBACK_VOICES = [
    {"ShortName": "en-US-AriaNeural", "Gender": "Female", "Locale": "en-US"},
    {"ShortName": "en-US-GuyNeural", "Gender": "Male", "Locale": "en-US"},
    {"ShortName": "en-US-JennyNeural", "Gender": "Female", "Locale": "en-US"},
    {"ShortName": "en-US-ChristopherNeural", "Gender": "Male", "Locale": "en-US"},
    {"ShortName": "en-GB-SoniaNeural", "Gender": "Female", "Locale": "en-GB"},
    {"ShortName": "en-GB-RyanNeural", "Gender": "Male", "Locale": "en-GB"},
    {"ShortName": "en-IN-NeerjaNeural", "Gender": "Female", "Locale": "en-IN"},
    {"ShortName": "en-IN-PrabhatNeural", "Gender": "Male", "Locale": "en-IN"},
]


def list_voices(locale_prefix: str = "") -> list[dict]:
    """Edge TTS voices (needs internet); falls back to a short built-in list offline."""
    try:
        import edge_tts

        voices = asyncio.run(asyncio.wait_for(edge_tts.list_voices(), 20))
    except Exception:  # noqa: BLE001 - offline or service error
        voices = FALLBACK_VOICES
    voices = [v for v in voices if v.get("ShortName", "").startswith(locale_prefix)]
    return sorted(voices, key=lambda v: v["ShortName"])
