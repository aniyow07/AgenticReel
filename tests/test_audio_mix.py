"""Music ducking: Remotion lowers the music while a narration caption is active (slow, real render)."""
import re
import shutil
import subprocess

import pytest

from rendering import remotion_runner
from schemas.render_props import RenderProps


def rms_db(path, start, dur):
    cp = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-ss", str(start), "-t", str(dur), "-i", str(path),
                         "-af", "astats=metadata=0", "-f", "null", "-"], capture_output=True, text=True)
    vals = re.findall(r"RMS level dB: (-?[\d.]+)", cp.stderr)
    return float(vals[-1])


@pytest.mark.slow
def test_music_is_ducked_under_speech(tmp_path):
    pub = tmp_path / "public"
    (pub / "audio").mkdir(parents=True)
    # self-generated test tone used as the "music" bed
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=4",
                    "-ar", "48000", "-ac", "2", str(pub / "audio" / "music.wav")], check=True)
    props = RenderProps.model_validate({
        "mode": "og", "fps": 30, "width": 270, "height": 480, "durationInFrames": 90,
        "music": {"src": "audio/music.wav", "volume": 0.5, "duckedVolume": 0.1},
        "captions": [{"id": "c1", "text": "speech here", "startFrame": 45, "endFrame": 90}],
        "scenes": [{"id": "s", "startFrame": 0, "durationInFrames": 90, "visualType": "title",
                    "params": {"title": "Ducking"}}]})
    res = remotion_runner.render(props, pub, tmp_path / "p.json", tmp_path / "o.mp4")
    assert res.ok, res.log_tail
    loud = rms_db(tmp_path / "o.mp4", 0.2, 0.9)     # no caption -> full music volume
    ducked = rms_db(tmp_path / "o.mp4", 1.8, 0.9)   # caption active -> ducked
    assert loud - ducked > 10  # 0.5 -> 0.1 is about 14 dB
