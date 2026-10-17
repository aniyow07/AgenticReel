import shutil
import subprocess
from pathlib import Path

import pytest

from agents import asset_generator
from agents.base import AgentFailure
from core import gameplay
from providers import tts as tts_mod
from schemas.artifacts import Script, ScriptSegment


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    m = tmp_path / "manifest.csv"
    monkeypatch.setattr(gameplay, "MANIFEST", m)
    return m


def test_missing_gameplay_gives_clear_error(manifest, make_ctx):
    with pytest.raises(gameplay.GameplayUnavailable, match="will not substitute"):
        gameplay.select_clips("minecraft", 10)
    ctx = make_ctx(mode="minecraft")
    with pytest.raises(AgentFailure, match="No usable minecraft gameplay"):
        asset_generator.prepare_gameplay(ctx, 5, 270, 480, 30)


def test_asset_validation_states(manifest, synthetic_clip, tmp_path):
    rec = gameplay.AssetRecord(asset_id="syn", relative_path=str(synthetic_clip), game="minecraft",
                               license="synthetic test pattern (unit test only)", review_status="needs_review")
    gameplay.fill_media_fields(rec)
    assert rec.width == "640" and rec.sha256
    assert gameplay.check_clip(rec).usable
    rec.review_status = "rejected"
    assert not gameplay.check_clip(rec).usable
    rec.review_status = "needs_review"
    missing = gameplay.AssetRecord(asset_id="m", relative_path=str(tmp_path / "nope.mp4"), game="minecraft")
    assert "file is missing" in gameplay.check_clip(missing).problems
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video at all" * 100)
    st = gameplay.check_clip(gameplay.AssetRecord(asset_id="b", relative_path=str(broken), game="minecraft"))
    assert not st.usable
    # file changed after it was recorded -> checksum mismatch is reported
    rec.sha256 = "0" * 64
    assert any("checksum" in p for p in gameplay.check_clip(rec).problems)


def test_usable_ranges_parse():
    r = gameplay.AssetRecord(asset_id="x", relative_path="x", duration_s="100", usable_ranges="5-20;30-29;90-200")
    assert r.windows() == [(5.0, 20.0), (90.0, 100.0)]


def test_background_prep_crops_without_distortion(manifest, synthetic_clip, make_ctx):
    """Renderer unit test with a SYNTHETIC pattern; this is not a gameplay test."""
    rec = gameplay.AssetRecord(asset_id="syn", relative_path=str(synthetic_clip), game="minecraft",
                               review_status="needs_review")
    gameplay.write_manifest([gameplay.fill_media_fields(rec)])
    ctx = make_ctx(mode="minecraft")
    out, ids = asset_generator.prepare_gameplay(ctx, 9.0, 270, 480, 30)  # longer than the 6s clip -> loops
    from rendering.media_utils import probe
    info = probe(out)
    assert (info.width, info.height) == (270, 480) and abs(info.duration - 9.0) < 0.15 and not info.has_audio
    assert ids == ["syn"]


class FailingTTS:
    name = "failing"

    def synthesize(self, text, out):
        raise tts_mod.TTSError("service down")


class EmptyTTS:
    name = "empty"

    def synthesize(self, text, out):
        Path(out).write_bytes(b"")
        tts_mod._measure(Path(out))  # raises: empty file is never accepted


def test_tts_failure_is_reported_not_faked(make_ctx, monkeypatch):
    ctx = make_ctx()
    monkeypatch.setattr(tts_mod, "provider_chain", lambda *a, **k: [FailingTTS(), EmptyTTS()])
    script = Script(title="T1", segments=[ScriptSegment(segment_id="N01", text="hello world")])
    with pytest.raises(AgentFailure, match="all TTS providers failed"):
        asset_generator.synthesize_segments(ctx, script)
    assert not (ctx.job.assets_dir / "audio" / "N01.json").exists()


def test_no_tts_backend(make_ctx, monkeypatch):
    ctx = make_ctx()
    monkeypatch.setattr(tts_mod, "provider_chain", lambda *a, **k: [])
    with pytest.raises(AgentFailure, match="No TTS backend"):
        asset_generator.synthesize_segments(ctx, Script(title="T1", segments=[
            ScriptSegment(segment_id="N01", text="hi there")]))


def test_tts_fallback_to_second_provider_and_cache(make_ctx, monkeypatch, tmp_path):
    calls = []

    class ToneTTS:
        name = "tone"

        def synthesize(self, text, out):
            calls.append(text)
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=1.2", "-ar", "48000", "-ac", "2", str(out)], check=True)
            return tts_mod.TTSResult(Path(out), tts_mod._measure(Path(out)), "tone", "test")
    ctx = make_ctx()
    monkeypatch.setattr(tts_mod, "provider_chain", lambda *a, **k: [FailingTTS(), ToneTTS()])
    script = Script(title="T1", segments=[ScriptSegment(segment_id="N01", text="hello world"),
                                          ScriptSegment(segment_id="N02", text="second chunk")])
    segs = asset_generator.synthesize_segments(ctx, script)
    assert [s.provider for s in segs] == ["tone", "tone"] and abs(segs[0].duration_s - 1.2) < 0.05
    narration = asset_generator.assemble_narration(ctx, segs, 0.1)
    from rendering.media_utils import probe
    assert abs(probe(narration).duration - 2.5) < 0.1
    asset_generator.synthesize_segments(ctx, script)
    assert len(calls) == 2  # second run reused the cached chunks
