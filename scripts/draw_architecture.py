"""Draws docs/architecture.png (a PNG rendering of docs/architecture.mmd) with Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1400, 1500
img = Image.new("RGB", (W, H), "#0B1020")
d = ImageDraw.Draw(img)


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


F, FB, FS = font(20), font(22, True), font(17)
boxes = {}


def box(key, x, y, w, h, title, sub="", color="#7C9CFF"):
    d.rounded_rectangle([x, y, x + w, y + h], 16, fill="#151C33", outline=color, width=3)
    d.text((x + w / 2, y + 22), title, font=FB, fill="#F5F7FF", anchor="mm")
    for i, line in enumerate(sub.split("\n") if sub else []):
        d.text((x + w / 2, y + 50 + i * 22), line, font=FS, fill="#A9B2D0", anchor="mm")
    boxes[key] = (x, y, w, h)


def arrow(a, b, color="#FFB547", label=""):
    ax, ay, aw, ah = boxes[a]
    bx, by, bw, bh = boxes[b]
    x1, y1 = ax + aw / 2, ay + ah
    x2, y2 = bx + bw / 2, by
    d.line([x1, y1, x2, y2], fill=color, width=3)
    d.polygon([(x2, y2), (x2 - 8, y2 - 14), (x2 + 8, y2 - 14)], fill=color)
    if label:
        d.text(((x1 + x2) / 2 + 10, (y1 + y2) / 2), label, font=FS, fill=color, anchor="lm")


d.text((W / 2, 40), "AgentReel architecture", font=font(34, True), fill="#F5F7FF", anchor="mm")
cx = W / 2 - 230
box("in", cx, 80, 460, 70, "User brief + mode + settings", "Streamlit app.py  ·  CLI run.py", "#FFB547")
box("p", cx, 190, 460, 70, "1  Planner", "plan.json")
box("r", cx, 290, 460, 90, "2  Researcher / RAG", "BM25 over PDF · DOCX · TXT · MD\nfacts.json (source + page + evidence)")
box("s", cx, 410, 460, 70, "3  Scriptwriter", "script.md + script.json")
box("b", cx, 510, 460, 70, "4  Storyboarder", "storyboard.json (parameters only, no code)")
box("a", cx, 610, 460, 70, "5  Asset Generator", "assets/manifest.json")
box("tts", 90, 730, 380, 90, "TTS per chunk", "Edge TTS / SAPI / supplied audio\nmeasured durations + word timings")
box("vis", 510, 730, 380, 90, "Visual assets", "real gameplay (trim/loop/crop)\nuser-supplied music")
box("man", 930, 730, 380, 90, "Manim templates", "process · flow · timeline · chart\nvalidated params only")
box("e", cx, 870, 460, 80, "6  Editor", "timeline · captions · SRT · render_props.json")
box("rr", cx, 990, 460, 80, "Remotion render", "OGVideo · MinecraftBrainrot · SubwayBrainrot")
box("ff", cx, 1110, 460, 80, "FFmpeg finish", "loudnorm -14 LUFS · H.264/AAC · size cap")
box("c", cx, 1230, 460, 80, "7  Critic / QA", "ffprobe + content checks · qa_report.json")
box("out", cx, 1360, 460, 70, "final.mp4 + captions.srt + logs", "run_log.jsonl · cost_report.csv", "#5BE38B")
box("llm", 1000, 300, 340, 110, "OpenRouter (optional)", "free models + fallbacks\nbounded retries · spend cap\nused by agents 1-4 and 7", "#A47CFF")
for a, b in [("in", "p"), ("p", "r"), ("r", "s"), ("s", "b"), ("b", "a"), ("a", "tts"), ("a", "vis"), ("a", "man"),
             ("tts", "e"), ("vis", "e"), ("man", "e"), ("e", "rr"), ("rr", "ff"), ("ff", "c")]:
    arrow(a, b)
arrow("c", "out", "#5BE38B", "pass")
# repair loop
x, y, w, h = boxes["c"]
sx, sy, sw, sh = boxes["s"]
d.line([x, y + h / 2, 60, y + h / 2, 60, sy + sh / 2, sx, sy + sh / 2], fill="#FF6B9A", width=3)
d.polygon([(sx, sy + sh / 2), (sx - 14, sy + sh / 2 - 8), (sx - 14, sy + sh / 2 + 8)], fill="#FF6B9A")
d.text((70, (y + sy) / 2), "fail → route to the\nresponsible stage\n(max 2 repairs)", font=FS, fill="#FF6B9A")
lx, ly, lw, lh = boxes["llm"]
for k in ("p", "r", "s", "b"):
    bx, by, bw, bh = boxes[k]
    d.line([lx, ly + lh / 2, bx + bw, by + bh / 2], fill="#A47CFF", width=2)
out = ROOT / "docs" / "architecture.png"
img.save(out)
print(out)
