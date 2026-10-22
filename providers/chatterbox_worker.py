"""Chatterbox-Turbo speech worker. Runs inside .venv-tts (its own PyTorch), never imported by the app.

providers/tts.py starts it once and keeps it alive, so the model loads once per app run. Protocol: one JSON
object per line. Requests on stdin, replies on stdout; everything the libraries print goes to stderr.

  ready line : {"ready": true, "device": "cuda", "sr": 24000, "load_s": 9.1}
  request    : {"text": "...", "out": "C:/.../raw.wav", "voice": "C:/.../ref.wav" or null, "words": true}
  reply      : {"ok": true, "duration_s": 3.2, "gen_s": 0.8, "words": [["Hello", 0.1, 0.4], ...], "vram_mb": 3100}
               {"ok": false, "error": "..."}

"words" are what Whisper heard with their times; providers/tts.py lines them up with the script text.
The worker exits by itself after IDLE_S seconds without a request, which frees the GPU memory.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time

IDLE_S = float(os.environ.get("CHATTERBOX_IDLE_S", "300"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--whisper", default=os.environ.get("CHATTERBOX_WHISPER", "small"))
    a = ap.parse_args()

    # keep stdout for the protocol only: anything printed by torch, transformers or C code goes to stderr
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def send(obj: dict) -> None:
        proto.write(json.dumps(obj) + "\n")
        proto.flush()

    t0 = time.time()
    try:
        import soundfile as sf
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = ChatterboxTurboTTS.from_local(a.model_dir, device)
    except Exception as e:  # noqa: BLE001 - reported to the app, which shows it
        send({"ready": False, "error": f"{type(e).__name__}: {e}"[:600]})
        return
    default_conds = model.conds
    conds: dict[str, object] = {}
    whisper = []  # loaded on first use

    def heard_words(path: str, text: str) -> list:
        if not whisper:
            from faster_whisper import WhisperModel
            try:
                whisper.append(WhisperModel(a.whisper, device="cuda", compute_type="float16") if device == "cuda"
                               else WhisperModel("tiny", device="cpu", compute_type="int8"))
            except Exception:  # noqa: BLE001 - no CUDA libraries for CTranslate2: CPU is fine for short clips
                whisper.append(WhisperModel("tiny", device="cpu", compute_type="int8"))
        import soxr  # hand Whisper 16 kHz samples directly: its own file decoder trips over newer PyAV
        audio, sr = sf.read(path, dtype="float32")
        audio = soxr.resample(audio, sr, 16000)
        segs, _ = whisper[0].transcribe(audio, language="en", word_timestamps=True, initial_prompt=text[:200],
                                        vad_filter=False, beam_size=1)
        return [[w.word.strip(), round(w.start, 3), round(w.end, 3)] for s in segs for w in (s.words or [])]

    send({"ready": True, "device": device, "sr": model.sr, "load_s": round(time.time() - t0, 2),
          "gpu": torch.cuda.get_device_name(0) if device == "cuda" else ""})

    lines: queue.Queue = queue.Queue()

    def read_stdin() -> None:
        for ln in sys.stdin:
            lines.put(ln)
        lines.put(None)  # the app closed the pipe

    threading.Thread(target=read_stdin, daemon=True).start()
    while True:
        try:
            line = lines.get(timeout=IDLE_S)
        except queue.Empty:
            return  # idle: exit so the GPU memory goes back to the rest of the app
        if line is None:
            return
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            ref = req.get("voice")
            if ref:
                if ref not in conds:
                    model.prepare_conditionals(ref)
                    conds[ref] = model.conds
                model.conds = conds[ref]
            else:
                model.conds = default_conds
            t1 = time.time()
            with torch.inference_mode():
                wav = model.generate(req["text"])
            sf.write(req["out"], wav.squeeze(0).float().cpu().numpy(), model.sr, subtype="PCM_16")
            gen_s = time.time() - t1
            words = heard_words(req["out"], req["text"]) if req.get("words") else []
            send({"ok": True, "duration_s": round(wav.shape[-1] / model.sr, 3), "gen_s": round(gen_s, 3),
                  "words": words,
                  "vram_mb": round(torch.cuda.max_memory_allocated() / 2**20) if device == "cuda" else 0})
        except Exception as e:  # noqa: BLE001
            send({"ok": False, "error": f"{type(e).__name__}: {e}"[:600]})


if __name__ == "__main__":
    main()
