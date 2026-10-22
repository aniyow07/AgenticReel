"""Text-to-speech providers.

Each provider writes one audio file per narration chunk and returns the
*measured* duration (ffprobe), plus word timings when the engine reports them.
A failed or empty synthesis raises TTSError; nothing is silently substituted.

Providers:
  chatterbox - Chatterbox-Turbo, a local neural voice on the GPU (the default; word times from Whisper)
  edge   - Microsoft Edge online voices via edge-tts (word boundaries available); dormant, TTS_ENGINE=edge
  sapi   - offline Windows SAPI voices via pyttsx3 (no word timings)
  supplied - user-provided narration audio (one file for the whole script)
"""
from __future__ import annotations

import asyncio
import atexit
import difflib
import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from rendering.media_utils import MediaError, probe, require_tool, run

ROOT = Path(__file__).resolve().parent.parent


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
    stats: dict = field(default_factory=dict)


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


# ---------------- Chatterbox-Turbo (local, GPU) ----------------
TAG = re.compile(r"\[[a-z ]{2,24}\]")  # paralinguistic tags such as [laugh]: performed, not spoken as words
VOICE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
VOICES_DIR = ROOT / "assets" / "voices"
DEFAULT_VOICE = "default"


def tts_python() -> Path:
    if os.environ.get("TTS_PYTHON"):
        return Path(os.environ["TTS_PYTHON"])
    venv = ROOT / ".venv-tts"
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def chatterbox_model_dir() -> Path:
    return Path(os.environ.get("CHATTERBOX_MODEL_DIR") or ROOT / "models" / "chatterbox-turbo")


def chatterbox_voices() -> list[dict]:
    """The model's built-in voice plus every reference clip (5-20 s of clean speech) in assets/voices.
    assets/voices/voices.json can give each clip a label, gender and accent:
    {"maya": {"label": "Maya", "gender": "Female", "accent": "Japanese"}}."""
    meta = {}
    try:
        meta = json.loads((VOICES_DIR / "voices.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass
    out = [{"id": DEFAULT_VOICE, "label": meta.get(DEFAULT_VOICE, {}).get("label", "Built-in"),
            "gender": meta.get(DEFAULT_VOICE, {}).get("gender", ""), "path": None}]
    if VOICES_DIR.is_dir():
        for p in sorted(VOICES_DIR.iterdir()):
            vid = p.stem.lower()
            if p.suffix.lower() in (".wav", ".mp3", ".flac") and VOICE_ID.match(vid) and vid != DEFAULT_VOICE:
                m = meta.get(vid, {})
                out.append({"id": vid, "label": m.get("label", vid.replace("_", " ").title()),
                            "gender": m.get("gender", ""), "accent": m.get("accent", ""), "path": str(p)})
    return out


def _tempo(rate: str) -> float:
    """'+10%' -> 1.10. Chatterbox has no speed setting, so speed is applied afterwards (pitch kept)."""
    try:
        pct = int(str(rate).strip().rstrip("%") or 0)
    except ValueError:
        pct = 0
    return max(0.5, min(2.0, 1 + pct / 100))


def align_words(text: str, heard: list, duration_s: float) -> list[tuple[str, float, float]]:
    """One (word, start, end) per whitespace word of `text`, timed from what Whisper heard. Words Whisper
    missed or heard differently share the gap between their matched neighbours by length. Returns [] when too
    little matched to trust (captions then fall back to proportional timing)."""
    words = TAG.sub(" ", text).split()
    heard = [(w, float(s), float(e)) for w, s, e in heard if re.sub(r"[^\w]", "", str(w))]
    if not words or not heard:
        return []
    norm = lambda w: re.sub(r"[^\w]", "", w.lower())  # noqa: E731
    sm = difflib.SequenceMatcher(None, [norm(w) for w in words], [norm(w) for w, _, _ in heard], autojunk=False)
    times: list[tuple[float, float] | None] = [None] * len(words)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            _, s, e = heard[blk.b + k]
            times[blk.a + k] = (s, e)
    if sum(t is not None for t in times) < max(1, 0.4 * len(words)):
        return []
    end_all = max(duration_s, heard[-1][2])
    i = 0
    while i < len(words):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(words) and times[j] is None:
            j += 1
        lo = times[i - 1][1] if i > 0 else 0.0
        hi = times[j][0] if j < len(words) else end_all
        hi = max(hi, lo)
        total = sum(len(w) + 1 for w in words[i:j])
        t = lo
        for k in range(i, j):
            d = (hi - lo) * (len(words[k]) + 1) / total
            times[k] = (round(t, 3), round(t + d, 3))
            t += d
        i = j
    out, last = [], 0.0
    for w, (s, e) in zip(words, times):  # keep times in order even if Whisper's were not
        s = max(s, last)
        e = max(e, s)
        out.append((w, s, e))
        last = s
    return out


class _Worker:
    """The Chatterbox process in .venv-tts. Started on first use and kept so the model loads once; it exits
    by itself after a few idle minutes (freeing GPU memory) and is restarted on the next request."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.info: dict = {}

    def _start(self, timeout_s: float) -> None:
        log = ROOT / "outputs" / "_tts_worker.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        # offline: everything is already on disk. A big CUDA kernel cache keeps the first clip after a start fast
        # on RTX 50 cards (about 20 s -> 4 s, measured).
        env = {"CUDA_CACHE_MAXSIZE": "4294967296", **os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
               "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            [str(tts_python()), "-u", str(Path(__file__).with_name("chatterbox_worker.py")),
             "--model-dir", str(chatterbox_model_dir())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(log, "ab"), env=env, cwd=str(ROOT),
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.lines = queue.Queue()
        out, lines = self.proc.stdout, self.lines

        def pump():
            for ln in out:
                lines.put(ln)
            lines.put(None)
        threading.Thread(target=pump, daemon=True).start()
        msg = self._read(timeout_s)
        if not msg.get("ready"):
            self.stop()
            raise TTSError(f"Chatterbox could not start: {msg.get('error', 'no reply')} (see outputs/_tts_worker.log)")
        self.info = msg

    def _read(self, timeout_s: float) -> dict:
        try:
            ln = self.lines.get(timeout=timeout_s)
        except queue.Empty:
            self.stop()
            raise TTSError(f"Chatterbox did not answer within {timeout_s:.0f}s") from None
        if ln is None:
            self.proc = None
            raise EOFError
        return json.loads(ln)

    def request(self, req: dict, timeout_s: float) -> dict:
        with self.lock:
            for attempt in (1, 2):  # the worker may have just exited for being idle: start it again once
                if self.proc is None or self.proc.poll() is not None:
                    try:
                        self._start(timeout_s=600)
                    except EOFError:
                        raise TTSError("Chatterbox exited while loading (see outputs/_tts_worker.log)") from None
                try:
                    self.proc.stdin.write(json.dumps(req) + "\n")
                    self.proc.stdin.flush()
                    return self._read(timeout_s)
                except (OSError, EOFError):
                    self.stop()
                    if attempt == 2:
                        raise TTSError("Chatterbox stopped unexpectedly (see outputs/_tts_worker.log)") from None
        raise TTSError("unreachable")

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.close()
                p.wait(5)
            except Exception:  # noqa: BLE001
                p.kill()


_worker = _Worker()
atexit.register(_worker.stop)


class ChatterboxTTS:
    name = "chatterbox"

    def __init__(self, voice: str = DEFAULT_VOICE, rate: str = "+0%", timeout_s: float = 180):
        self.voice, self.rate, self.timeout_s = voice or DEFAULT_VOICE, rate, timeout_s

    @staticmethod
    def available() -> bool:
        d = chatterbox_model_dir()
        return tts_python().is_file() and (d / "t3_turbo_v1.safetensors").is_file() \
            and (d / "s3gen_meanflow.safetensors").is_file()

    def synthesize(self, text: str, out_wav: Path) -> TTSResult:
        t0 = time.time()
        known = {v["id"]: v for v in chatterbox_voices()}
        v = known.get(self.voice) or known[DEFAULT_VOICE]  # e.g. an old Edge voice name: use the default voice
        raw = out_wav.with_name(out_wav.stem + "_cb.wav")
        side = raw.with_suffix(".json")
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        # The raw take is kept: every take of a line comes out a little different, so a speed change reuses
        # it (only the tempo is applied again) and the length change is exactly the one asked for.
        key = hashlib.sha256(json.dumps([text, v["path"]]).encode()).hexdigest()[:16]
        r = None
        if raw.exists() and side.exists():
            try:
                old = json.loads(side.read_text(encoding="utf-8"))
                r = old["reply"] if old.get("key") == key else None
            except (ValueError, KeyError):
                r = None
        if r is None:
            r = _worker.request({"text": text, "out": str(raw.resolve()), "voice": v["path"], "words": True},
                                self.timeout_s)
            if not r.get("ok"):
                raise TTSError(f"Chatterbox failed: {r.get('error', 'unknown error')}")
            if not raw.exists() or raw.stat().st_size < 1000:
                raise TTSError("Chatterbox returned no audio")
            side.write_text(json.dumps({"key": key, "reply": r}), encoding="utf-8")
        tempo = _tempo(self.rate)
        cmd = [require_tool("ffmpeg"), "-v", "error", "-y", "-i", str(raw)]
        if abs(tempo - 1) > 1e-3:
            cmd += ["-af", f"atempo={tempo:.3f}"]
        cp = run(cmd + ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)], timeout=120)
        if cp.returncode != 0:
            raise TTSError(f"could not convert Chatterbox audio: {cp.stderr[:300]}")
        dur = _measure(out_wav)
        words = [(w, round(s / tempo, 3), round(e / tempo, 3))
                 for w, s, e in align_words(text, r.get("words", []), r.get("duration_s", dur * tempo))]
        res = TTSResult(out_wav, dur, self.name, v["id"], words, time.time() - t0)
        res.stats = {k: r.get(k) for k in ("gen_s", "vram_mb")} | {"device": _worker.info.get("device")}
        return res


def engine() -> str:
    """Which voice engine the app uses: chatterbox (default) or edge (the old online voices, kept dormant)."""
    import core.config  # noqa: F401 - loads .env

    return (os.environ.get("TTS_ENGINE") or "chatterbox").strip().lower()


def get_provider(name: str, voice: str, rate: str):
    if name == "chatterbox":
        return ChatterboxTTS(voice=voice, rate=rate)
    if name == "edge":
        return EdgeTTS(voice=voice, rate=rate)
    if name == "sapi":
        return SapiTTS()
    raise TTSError(f"unknown TTS provider {name!r}")


def provider_chain(preferred: str, voice: str, rate: str, local_only: bool) -> list:
    """Preferred provider first. Chatterbox gets no fallback: a robotic SAPI voice in the middle of a video is
    worse than a clear error. Edge falls back to offline SAPI. Edge needs the network, so LOCAL_ONLY
    still allows it only if explicitly preferred (it is TTS, not an LLM call)."""
    if preferred == "chatterbox":
        return [ChatterboxTTS(voice=voice, rate=rate)] if ChatterboxTTS.available() else []
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
    {"ShortName": "ja-JP-KeitaNeural", "Gender": "Male", "Locale": "ja-JP"},
    {"ShortName": "ja-JP-NanamiNeural", "Gender": "Female", "Locale": "ja-JP"},
]


def list_voices(locale_prefix: str = "", engine_name: str = "") -> list[dict]:
    """The voices of an engine (default: TTS_ENGINE). Chatterbox: the built-in voice and the clips in
    assets/voices. Edge: its online list, or a short built-in list offline."""
    if (engine_name or engine()) == "chatterbox":
        return [{"ShortName": v["id"], "Gender": v["gender"], "Locale": "en", "Label": v["label"]}
                for v in chatterbox_voices()]
    try:
        import edge_tts

        voices = asyncio.run(asyncio.wait_for(edge_tts.list_voices(), 20))
    except Exception:  # noqa: BLE001 - offline or service error
        voices = FALLBACK_VOICES
    voices = [v for v in voices if v.get("ShortName", "").startswith(locale_prefix)]
    return sorted(voices, key=lambda v: v["ShortName"])
