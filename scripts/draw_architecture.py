"""Draws docs/architecture.png (the picture of docs/architecture.mmd) with Pillow.

    python scripts/draw_architecture.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1800, 1780
BG, CARD, TEXT, MUTED = "#0B1020", "#151C33", "#F5F7FF", "#A9B2D0"
BLUE, AMBER, GREEN, PINK, VIOLET, TEAL = "#7C9CFF", "#FFB547", "#5BE38B", "#FF6B9A", "#A47CFF", "#4FD1C5"
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


FB, FS, FT, FG = font(23, True), font(17), font(40, True), font(20, True)
boxes = {}


def box(key, x, y, w, h, title, sub="", color=BLUE):
    d.rounded_rectangle([x, y, x + w, y + h], 14, fill=CARD, outline=color, width=3)
    d.text((x + w / 2, y + 24), title, font=FB, fill=TEXT, anchor="mm")
    for i, line in enumerate(sub.split("\n") if sub else []):
        d.text((x + w / 2, y + 52 + i * 21), line, font=FS, fill=MUTED, anchor="mm")
    boxes[key] = (x, y, w, h)


def group(x, y, w, h, title, color):
    d.rounded_rectangle([x, y, x + w, y + h], 20, outline=color, width=2)
    tw = d.textlength(title, font=FG)
    d.rectangle([x + 22, y - 13, x + 40 + tw, y + 13], fill=BG)
    d.text((x + 31, y), title, font=FG, fill=color, anchor="lm")


def head(x2, y2, dx, dy, color):
    if dy:
        s = 1 if dy > 0 else -1
        d.polygon([(x2, y2), (x2 - 8, y2 - 14 * s), (x2 + 8, y2 - 14 * s)], fill=color)
    else:
        s = 1 if dx > 0 else -1
        d.polygon([(x2, y2), (x2 - 14 * s, y2 - 8), (x2 - 14 * s, y2 + 8)], fill=color)


def mid_y(k):
    return boxes[k][1] + boxes[k][3] / 2


def right(k):
    return boxes[k][0] + boxes[k][2]


def down(a, b, color=AMBER, ax=None, bx=None):
    x0, y0, w0, h0 = boxes[a]
    x1, y1, w1, h1 = boxes[b]
    sx = ax if ax is not None else x0 + w0 / 2
    ex = bx if bx is not None else x1 + w1 / 2
    sy, ey = y0 + h0, y1
    if abs(sx - ex) < 1:
        d.line([sx, sy, ex, ey], fill=color, width=3)
    else:
        my = (sy + ey) / 2
        d.line([sx, sy, sx, my, ex, my, ex, ey], fill=color, width=3)
    head(ex, ey, 0, 1, color)


def lane(src, lx, dst, color, label="", dy=0):
    """Right edge of src -> across to lane x -> along the lane -> into the left edge of dst (dy shifts the start
    so it does not sit on top of the AI-call line from the same box)."""
    sy, ey = mid_y(src) + dy, mid_y(dst)
    d.line([right(src), sy, lx, sy, lx, ey, boxes[dst][0], ey], fill=color, width=2)
    head(boxes[dst][0], ey, 1, 0, color)
    if label:
        d.text((lx + 6, ey - 14), label, font=FS, fill=color, anchor="lm")


d.text((W / 2, 46), "AgentReel architecture", font=FT, fill=TEXT, anchor="mm")
d.text((W / 2, 86), "seven agents · schema-checked hand-offs · RAG grounding · critic repair loop · Manim + Remotion",
       font=FS, fill=MUTED, anchor="mm")

# ---------------- entry points ----------------
group(40, 130, 1720, 150, "How you start it", AMBER)
box("web", 70, 160, 520, 96, "Web app  ·  web.py", "webui/ (ES modules)  <->  webapp/ local API\n/api/jobs · upload · version · resume · delete", AMBER)
box("cli", 640, 160, 520, 96, "CLI  ·  run.py", "--topic / --brief · --provider · --seed\n--resume · --rerender · --fresh-script", AMBER)
box("st", 1210, 160, 520, 96, "Streamlit  ·  app.py", "older UI over the same pipeline", AMBER)

box("orch", 470, 330, 860, 100, "Orchestrator  ·  orchestrator.py (Pipeline)",
    "state.json per job · stage fingerprints -> cache & resume\ncontent cache: same brief + sources reuses plan/script across versions", TEXT)

# ---------------- agents ----------------
group(40, 480, 1120, 1000, "Agents  (agents/*.py)", BLUE)
ax, aw = 120, 560
box("p", ax, 520, aw, 78, "1  Planner", "plan.json · scene count, Manim beats, research needs")
box("r", ax, 640, aw, 78, "2  Researcher (RAG)", "facts.json · claim + source + page + evidence")
box("s", ax, 760, aw, 78, "3  Scriptwriter", "script.json · lines cite fact_ids · word budget")
box("b", ax, 880, aw, 78, "4  Storyboarder", "storyboard.json · visual + params + backdrop per scene")
box("a", ax, 1000, aw, 78, "5  Asset Generator", "assets/manifest.json + .csv (sources, licences)")
box("tts", 60, 1110, 330, 96, "Voice (TTS)", "Edge TTS · SAPI · your audio\nmeasured lengths + word timings", TEAL)
box("vis", 405, 1110, 320, 96, "Footage & music", "gameplay cut from the middle\nlicence status in manifest", TEAL)
box("man", 740, 1110, 330, 96, "Manim (17 templates)", "5 looks · transparent WebM\nparams validated, no code run", TEAL)
box("e", ax, 1240, aw, 78, "6  Editor", "render_props.json · captions.json · captions.srt")
box("c", ax, 1360, aw, 78, "7  Critic / QA", "qa_report.json · ~30 checks + AI review")

# ---------------- right column ----------------
RX, RW = 1230, 500
group(1200, 480, 560, 470, "AI provider routing  (providers/)", VIOLET)
box("gem", RX, 520, RW, 110, "Gemini", "gemini-3.8-flash -> 3.5-flash-lite\npacing 6 s · per-minute waits · daily quota skip", VIOLET)
box("orr", RX, 650, RW, 110, "OpenRouter", "free models first -> fallbacks\nretries with backoff · global spend cap", VIOLET)
box("mode", RX, 780, RW, 140, "Execution mode", "AI_PREFERRED: fall back to local templates\nAI_REQUIRED: stop if the AI is unavailable\nLOCAL_ONLY: no API calls\nevery reply = JSON validated by Pydantic", VIOLET)

group(1200, 990, 560, 280, "Grounding  (retrieval/ + checks)", GREEN)
box("rag", RX, 1030, RW, 96, "Ingest + BM25+ retrieval", "PDF · DOCX · TXT · MD -> passages + page numbers\noptional Wikipedia (off by default)", GREEN)
box("gr", RX, 1146, RW, 96, "Grounding checks", "numbers must appear verbatim in evidence\nunsupported text, links, contacts stripped", GREEN)

group(1200, 1310, 560, 380, "Render  (rendering/ + remotion/)", TEAL)
box("rem", RX, 1350, RW, 96, "Remotion", "OGVideo (12 backdrops) · Brainrot videos\nZod-checked props · frame progress to UI", TEAL)
box("ff", RX, 1466, RW, 96, "FFmpeg finish", "loudnorm -14 LUFS · H.264 / AAC · 30 fps\nsize cap · ffprobe validation", TEAL)
box("fin", RX, 1582, RW, 86, "final.mp4 + captions.srt", "checked by the Critic before it is done", GREEN)

group(40, 1530, 1120, 170, "Logs per job  (outputs/<job>/logs)", MUTED)
box("logs", 70, 1565, 1060, 110, "run_log.jsonl · cost_report.csv · interventions.md",
    "every step, model, prompt version, tokens, latency, retry and repair\ncost: measured or estimated · interventions only when a person steps in", MUTED)

# ---------------- arrows ----------------
for k in ("web", "cli", "st"):
    down(k, "orch")
down("orch", "p", ax=600, bx=ax + aw / 2)
for a2, b2 in [("p", "r"), ("r", "s"), ("s", "b"), ("b", "a")]:
    down(a2, b2)
for t in ("tts", "vis", "man"):
    down("a", t, TEAL)
    down(t, "e", TEAL)
down("e", "c")

# critic repair loop
x, y, w, h = boxes["c"]
sx, sy, sw, sh = boxes["s"]
d.line([x, y + h / 2, 82, y + h / 2, 82, sy + sh / 2, sx, sy + sh / 2], fill=PINK, width=3)
head(sx, sy + sh / 2, 1, 0, PINK)
d.text((x, y + h + 18), "QA fails -> back to the stage that caused it (script, storyboard or edit), max 2 repairs",
       font=FS, fill=PINK, anchor="lm")

# AI calls: agents 1-4 and 7 share one bus into the provider router
BUS = 1100
for k in ("p", "r", "s", "b", "c"):
    d.line([right(k), mid_y(k), BUS, mid_y(k)], fill=VIOLET, width=2)
d.line([BUS, mid_y("p"), BUS, mid_y("c")], fill=VIOLET, width=3)
for k in ("gem", "orr", "mode"):
    d.line([BUS, mid_y(k), boxes[k][0], mid_y(k)], fill=VIOLET, width=2)
    head(boxes[k][0], mid_y(k), 1, 0, VIOLET)
d.text((BUS - 8, mid_y("p") - 16), "AI calls (agents 1-4 and 7)", font=FS, fill=VIOLET, anchor="rm")

# grounding: researcher retrieves, storyboarder (and scriptwriter) are checked
lane("r", 1140, "rag", GREEN, dy=16)
lane("b", 1165, "gr", GREEN, dy=16)
# render path
lane("e", 1185, "rem", TEAL)
down("rem", "ff", TEAL)
down("ff", "fin", GREEN)

d.text((W / 2, H - 28), "docs/architecture.mmd is the same graph as text", font=FS, fill=MUTED, anchor="mm")
out = ROOT / "docs" / "architecture.png"
img.save(out)
print(out)
