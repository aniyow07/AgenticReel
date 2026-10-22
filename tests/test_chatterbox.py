"""Chatterbox-Turbo wiring, without the model: word alignment, voices, speed, engine switch."""
import shutil
import subprocess

import pytest

from providers import tts


def test_align_words_times_every_script_word():
    heard = [["Bees", 0.1, 0.4], ["make", 0.45, 0.7], ["honey", 0.75, 1.1], ["from", 1.2, 1.4],
             ["nectar.", 1.45, 2.0]]
    out = tts.align_words("Bees make honey from nectar.", heard, 2.2)
    assert [w for w, _, _ in out] == ["Bees", "make", "honey", "from", "nectar."]
    assert out[2] == ("honey", 0.75, 1.1)


def test_align_words_fills_words_whisper_heard_differently():
    # Whisper wrote "20" as "twenty"; the unmatched word gets the gap between its neighbours
    heard = [["About", 0.0, 0.3], ["twenty", 0.35, 0.8], ["species", 0.9, 1.5]]
    out = tts.align_words("About 20 species", heard, 1.6)
    assert len(out) == 3 and out[1][0] == "20"
    assert 0.3 <= out[1][1] <= out[1][2] <= 0.9


def test_align_words_skips_tags_and_gives_up_on_garbage():
    heard = [["Wait", 0.0, 0.3], ["what", 0.9, 1.2]]
    out = tts.align_words("Wait [laugh] what", heard, 1.3)
    assert [w for w, _, _ in out] == ["Wait", "what"]
    assert tts.align_words("Completely different words here", [["zzz", 0, 1]], 1.0) == []
    assert tts.align_words("Hello", [], 1.0) == []


def test_tempo_from_rate():
    assert tts._tempo("+10%") == pytest.approx(1.1)
    assert tts._tempo("-20%") == pytest.approx(0.8)
    assert tts._tempo("junk") == 1.0


def test_voices_are_builtin_plus_reference_clips(tmp_path, monkeypatch):
    (tmp_path / "maya.wav").write_bytes(b"x")
    (tmp_path / "Bad Name!.wav").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "voices.json").write_text('{"maya": {"label": "Maya", "gender": "Female"}}')
    monkeypatch.setattr(tts, "VOICES_DIR", tmp_path)
    vs = tts.chatterbox_voices()
    assert [v["id"] for v in vs] == ["default", "maya"]
    assert vs[1]["label"] == "Maya" and vs[1]["gender"] == "Female" and vs[0]["path"] is None


def test_engine_switch(monkeypatch):
    from core.config import Settings
    monkeypatch.delenv("TTS_ENGINE", raising=False)
    s = Settings.from_env()
    assert s.tts_provider == "chatterbox" and tts.engine() == "chatterbox"
    monkeypatch.setenv("TTS_ENGINE", "edge")
    monkeypatch.setenv("TTS_PROVIDER", "edge")
    monkeypatch.setenv("TTS_VOICE", "en-US-GuyNeural")
    s = Settings.from_env()
    assert (s.tts_provider, s.tts_voice) == ("edge", "en-US-GuyNeural")


def test_chatterbox_pace_raises_the_word_budget():
    from types import SimpleNamespace

    from agents.base import AgentContext, words_budget
    from schemas.brief import Brief
    ctx = AgentContext(job=None, brief=Brief(topic="Bees"), settings=SimpleNamespace(tts_provider="chatterbox"),
                       llm=None)
    assert ctx.pace == 1.18
    # speech fills the middle of the 42-48 s window minus the 1 s closing tail and ~2% of pauses
    assert words_budget(45, "og", 10, ctx.pace) == int((45 * 0.98 - 1.0) * 140 * 1.1 * 1.18 / 60)


def test_each_video_can_pick_its_engine_and_keeps_a_matching_voice():
    from types import SimpleNamespace

    from agents.base import AgentContext
    from schemas.brief import Brief
    s = SimpleNamespace(tts_provider="chatterbox", tts_voice="default", chatterbox_voice="default",
                        edge_voice="en-US-AriaNeural")
    ctx = lambda **kw: AgentContext(job=None, brief=Brief(topic="Bees", **kw), settings=s, llm=None)  # noqa: E731
    assert (ctx().tts_provider, ctx().voice, ctx().pace) == ("chatterbox", "default", 1.18)
    assert (ctx(voice="kai").voice) == "kai"
    edge = ctx(tts_engine="edge", voice="ja-JP-KeitaNeural")
    assert (edge.tts_provider, edge.voice, edge.pace) == ("edge", "ja-JP-KeitaNeural", 1.0)
    assert ctx(tts_engine="edge", voice="kai").voice == "en-US-AriaNeural"  # a Natural voice on Classic -> its default
    assert ctx(voice="en-US-GuyNeural").voice == "default"  # an old Edge voice on Natural -> the built-in voice


def test_version_and_new_job_keep_the_engine(monkeypatch, tmp_path):
    from webapp import runner
    seen = []
    monkeypatch.setattr(runner, "_run", lambda brief, *a, **k: seen.append(brief) or "job")
    runner.new_job({"topic": "Bees and honey", "tts_engine": "edge", "voice": "ja-JP-NanamiNeural"})
    runner.new_job({"topic": "Bees and honey", "tts_engine": "bogus"})
    assert seen[0].tts_engine == "edge" and seen[0].voice == "ja-JP-NanamiNeural" and seen[1].tts_engine == ""
    (tmp_path / "brief.json").write_text(seen[0].model_dump_json())
    runner.new_version(tmp_path, {"mode": "og", "voice": "kai", "tts_engine": "chatterbox"})
    assert (seen[2].tts_engine, seen[2].voice) == ("chatterbox", "kai")
    runner.new_version(tmp_path, {"mode": "og"})
    assert seen[3].tts_engine == "edge"  # a version keeps the original's engine unless another is picked


def test_no_silent_fallback_when_model_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATTERBOX_MODEL_DIR", str(tmp_path))
    assert tts.provider_chain("chatterbox", "default", "+0%", True) == []


def test_brief_accepts_chatterbox_and_old_edge_voices():
    from schemas.brief import Brief
    assert Brief(topic="Bees", voice="maya").voice == "maya"
    assert Brief(topic="Bees", voice="en-US-GuyNeural").voice == "en-US-GuyNeural"
    with pytest.raises(Exception):
        Brief(topic="Bees", voice="rm -rf /")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_synthesize_applies_speed_and_scales_word_times(tmp_path, monkeypatch):
    calls = []

    def fake_request(req, timeout_s):
        calls.append(req)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=2", "-ar", "24000",
                        req["out"]], check=True)
        return {"ok": True, "duration_s": 2.0, "gen_s": 0.5, "vram_mb": 3000,
                "words": [["Hello", 0.0, 0.8], ["there", 1.0, 2.0]]}
    monkeypatch.setattr(tts._worker, "request", fake_request)
    r = tts.ChatterboxTTS(voice="someone-unknown", rate="+25%").synthesize("Hello there", tmp_path / "N01.wav")
    assert r.provider == "chatterbox" and r.voice == "default"  # unknown (e.g. old Edge) voice -> built-in
    assert r.duration_s == pytest.approx(1.6, abs=0.05)
    assert r.word_timings[1] == ("there", 0.8, 1.6)
    # the raw take is kept: another speed reuses it (same words, exact tempo change) instead of a new take
    r2 = tts.ChatterboxTTS(voice="default", rate="+0%").synthesize("Hello there", tmp_path / "N01.wav")
    assert len(calls) == 1 and r2.duration_s == pytest.approx(2.0, abs=0.05)
    assert r2.word_timings[1] == ("there", 1.0, 2.0)
    tts.ChatterboxTTS(voice="default", rate="+0%").synthesize("Hello again", tmp_path / "N01.wav")
    assert len(calls) == 2  # different text: a new take


def test_caption_text_never_shows_voice_tags():
    from rendering.timeline import build_captions, layout_segments
    from schemas.artifacts import SegmentAudio
    seg = SegmentAudio(segment_id="N01", path="a.wav", duration_s=2.0, provider="chatterbox",
                       word_timings=[("Wait", 0.0, 0.5), ("what", 1.0, 1.5)])
    caps = build_captions({"N01": "Wait [laugh] what"}, [seg], layout_segments([seg], gap_s=0.1))
    assert "laugh" not in " ".join(c.text for c in caps)
    assert caps[0].alignment == "tts_word_boundaries"
