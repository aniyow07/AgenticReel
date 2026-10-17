"""AgentReel Streamlit control panel.

    streamlit run app.py                         # provider from .env (LLM_PROVIDER)
    streamlit run app.py -- --provider gemini    # or openrouter

The UI only collects settings and shows real job state read from outputs/<job>/state.json.
Rendering happens in the same Python pipeline the CLI uses (run.py).
"""
from __future__ import annotations

import csv
import html
import io
import json
import secrets
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.config import Settings  # noqa: E402
from core.gameplay import library_status  # noqa: E402
from core.jobs import STAGE_LABELS, STAGES, list_jobs, safe_filename  # noqa: E402
from rendering import manim_runner, remotion_runner  # noqa: E402
from rendering.media_utils import tool_path  # noqa: E402
from schemas.brief import PROD_MAX_S, PROD_MIN_S, Brief  # noqa: E402

st.set_page_config(page_title="AgentReel", page_icon=":material/movie:", layout="wide",
                   initial_sidebar_state="collapsed")


def _launch_args() -> None:
    """`streamlit run app.py -- --provider gemini` picks the LLM provider for this server."""
    import argparse
    import os
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--provider", choices=["openrouter", "gemini"])
    ap.add_argument("--gemini-interval", type=float)
    a, _ = ap.parse_known_args(sys.argv[1:])
    if a.provider:
        os.environ["LLM_PROVIDER"] = a.provider
    if a.gemini_interval is not None:
        os.environ["GEMINI_MIN_INTERVAL_S"] = str(a.gemini_interval)


_launch_args()

UI_ASSETS = ROOT / "assets" / "ui"
MODES = {
    "og": ("Motion graphics", "Animated titles, charts and Manim diagrams."),
    "minecraft": ("Minecraft", "Narration over Minecraft parkour."),
    "subway": ("Subway Surfers", "Narration over Subway Surfers runs."),
}
CONTENT_TYPES = {
    "factual_explainer": "Explainer", "promotional": "Promotion", "awareness": "Awareness",
    "fictional_story": "Story (fiction)", "general_entertainment": "Entertainment",
    "educational_story": "Educational story", "opinion_commentary": "Opinion / commentary",
}
EXEC_MODES = {
    "AI_PREFERRED": "AI, with template fallback",
    "LOCAL_ONLY": "Templates only (offline)",
    "AI_REQUIRED": "AI only",
}
FORMATS = {"video_9x16": "9:16", "video_16x9": "16:9"}
MOTION = {"auto": "Auto", "subtle": "Subtle", "strong": "Strong", "off": "Off"}
STATUS_TEXT = {
    "created": ("Starting", "neutral"), "running": ("Rendering", "info"), "completed": ("Ready", "ok"),
    "completed_with_warnings": ("Ready", "ok"), "failed_qa": ("Checks failed", "warn"),
    "failed": ("Failed", "bad"), "interrupted": ("Interrupted", "warn"),
}
SOURCE_EXT = {".pdf", ".docx", ".txt", ".md"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
MAX_UPLOAD_MB = 50

BG, SURFACE, SURFACE2, LINE = "#0D0E10", "#151619", "#1C1D21", "#26282D"
TEXT, MUTED, ACCENT = "#E9E9E6", "#8E9299", "#3DDC97"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, .stMarkdown, p, label, button, input, textarea, [data-baseweb="select"] div {{
  font-family: 'Inter', system-ui, sans-serif !important; }}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
/* remove Streamlit chrome */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
#MainMenu, footer, [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
.stApp {{ background: {BG}; }}
.block-container {{ max-width: 1360px; padding: 1.4rem 2rem 3rem 2rem; }}
p, label, .stMarkdown {{ color: {TEXT}; }}
/* labels */
[data-testid="stWidgetLabel"] p {{ font-size: .78rem !important; font-weight: 500; color: {MUTED} !important;
  letter-spacing: .01em; }}
/* inputs */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-testid="stNumberInput"] > div {{
  background: {SURFACE2} !important; border: 1px solid {LINE} !important; border-radius: 10px !important; }}
[data-baseweb="input"] input, textarea {{ background: transparent !important; color: {TEXT} !important; }}
textarea {{ font-size: .98rem !important; line-height: 1.5 !important; }}
[data-baseweb="textarea"]:focus-within, [data-baseweb="input"]:focus-within {{ border-color: {ACCENT} !important; }}
[data-testid="stFileUploaderDropzone"] {{ background: {SURFACE2}; border: 1px dashed {LINE}; border-radius: 10px;
  padding: .6rem .9rem; }}
[data-testid="stFileUploaderDropzoneInstructions"] span {{ color: {MUTED}; font-size: .82rem; }}
/* buttons */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {{
  border-radius: 10px; border: 1px solid {LINE}; background: {SURFACE2}; color: {TEXT}; font-weight: 500;
  min-height: 2.5rem; }}
.stButton button:hover, .stDownloadButton button:hover {{ border-color: #3A3C42; color: #fff; }}
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {ACCENT} !important; border: none !important; }}
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-primaryFormSubmit"] p {{
  color: #08110D !important; font-weight: 600 !important; }}
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: #5BE6AA !important; }}
button[data-testid="stBaseButton-primary"]:disabled {{ background: {SURFACE2} !important; }}
button[data-testid="stBaseButton-primary"]:disabled p {{ color: {MUTED} !important; }}
/* expanders */
[data-testid="stExpander"] details {{ background: transparent; border: 1px solid {LINE}; border-radius: 10px; }}
[data-testid="stExpander"] summary p {{ font-size: .88rem; color: {TEXT}; }}
/* tabs */
[data-baseweb="tab-list"] {{ gap: 1.4rem; border-bottom: 1px solid {LINE}; }}
[data-baseweb="tab"] p {{ font-size: .88rem; }}
[data-baseweb="tab-highlight"] {{ background: {ACCENT}; }}
/* panels */
.st-key-panel {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; padding: 1.1rem 1.1rem .8rem; }}
.st-key-stage {{ background: radial-gradient(120% 90% at 50% 0%, #17191D 0%, {BG} 70%); border: 1px solid {LINE};
  border-radius: 16px; padding: 1.4rem; min-height: 640px; }}
.st-key-stage video {{ max-height: 600px; width: auto !important; max-width: 100%; display: block; margin: 0 auto;
  border-radius: 12px; background: #000; }}
/* style cards */
[class*="st-key-card_"] {{ border: 1px solid {LINE}; border-radius: 12px; padding: 6px; background: {SURFACE2};
  transition: border-color .15s; gap: .35rem !important; }}
[class*="st-key-card_"]:hover {{ border-color: #3A3C42; }}
[class*="st-key-card_"][class*="_on"] {{ border-color: {ACCENT}; box-shadow: 0 0 0 1px {ACCENT} inset; }}
[class*="st-key-card_"] img {{ border-radius: 8px; aspect-ratio: 1 / 1; object-fit: cover; }}
[class*="st-key-card_"] .stButton button {{ background: transparent; border: none; min-height: 1.6rem; padding: 0;
  font-size: .82rem; font-weight: 600; }}
[class*="st-key-card_"][class*="_on"] .stButton button {{ color: {ACCENT}; }}
/* custom bits */
.ar-top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom: 1rem; }}
.ar-logo {{ font-weight: 700; font-size: 1.15rem; letter-spacing: -.01em; color: {TEXT}; display:flex; gap:.55rem;
  align-items:center; }}
.ar-logo .mark {{ width: 22px; height: 22px; border-radius: 6px; background: {ACCENT}; display:inline-block;
  position:relative; }}
.ar-logo .mark::after {{ content:''; position:absolute; left:8px; top:6px; border-left:8px solid #08110D;
  border-top:5px solid transparent; border-bottom:5px solid transparent; }}
.ar-meta {{ color: {MUTED}; font-size: .8rem; text-align: right; }}
.ar-meta b {{ color: {TEXT}; font-weight: 500; }}
.ar-section {{ font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: {MUTED};
  margin: .3rem 0 .45rem 0; }}
.ar-caption {{ color: {MUTED}; font-size: .8rem; margin-top: .4rem; }}
.ar-stagehead {{ display:flex; justify-content:space-between; align-items:flex-start; gap: 1rem; margin-bottom: 1rem; }}
.ar-stagehead .t {{ font-size: 1.05rem; font-weight: 600; color: {TEXT}; line-height: 1.35; }}
.ar-stagehead .s {{ color: {MUTED}; font-size: .8rem; margin-top: .2rem; }}
.ar-pill {{ display:inline-block; padding:.18rem .6rem; border-radius:999px; font-size:.74rem; font-weight:600;
  white-space: nowrap; }}
.ar-pill.ok {{ background:#123A2A; color:#5FE3A8; }} .ar-pill.info {{ background:#14293F; color:#7DB8F2; }}
.ar-pill.warn {{ background:#3A2D12; color:#F0C266; }} .ar-pill.bad {{ background:#3D1714; color:#F08A7E; }}
.ar-pill.neutral {{ background:{SURFACE2}; color:{MUTED}; }}
.ar-example {{ text-align:center; color:{MUTED}; font-size:.8rem; margin-top:.8rem; }}
.ar-progress {{ max-width: 420px; margin: 3.5rem auto 0 auto; }}
.ar-progress .now {{ font-size: 1.05rem; font-weight: 600; color: {TEXT}; margin-bottom: .35rem; }}
.ar-progress .sub {{ color: {MUTED}; font-size: .82rem; margin-bottom: 1rem; }}
.ar-bar {{ height: 4px; border-radius: 4px; background: {SURFACE2}; overflow: hidden; margin-bottom: 1.4rem; }}
.ar-bar > div {{ height: 100%; background: {ACCENT}; border-radius: 4px; }}
.ar-stage {{ display:flex; align-items:center; gap:.65rem; font-size:.86rem; color:{MUTED}; padding:.28rem 0; }}
.ar-dot {{ width:7px; height:7px; border-radius:50%; background:#33363C; flex:none; }}
.ar-dot.done {{ background:{ACCENT}; }} .ar-dot.running {{ background:#7DB8F2; box-shadow:0 0 0 4px #14293F; }}
.ar-dot.failed {{ background:#F08A7E; }} .ar-dot.skipped {{ background:#55595F; }} .ar-dot.stale {{ background:#F0C266; }}
.ar-stage.done {{ color:#B9BCC1; }} .ar-stage.running {{ color:{TEXT}; font-weight:600; }}
.ar-facts {{ display:flex; flex-wrap:wrap; gap:.5rem; justify-content:center; margin: 1rem 0 .4rem 0; }}
.ar-fact {{ background:{SURFACE2}; border:1px solid {LINE}; border-radius:999px; padding:.25rem .7rem; font-size:.78rem;
  color:#C4C7CC; }}
.ar-row {{ display:flex; align-items:center; gap:1rem; padding:.7rem .2rem; border-bottom:1px solid {LINE}; }}
.ar-row .t {{ color:{TEXT}; font-size:.9rem; font-weight:500; }} .ar-row .s {{ color:{MUTED}; font-size:.78rem; }}
[class*="st-key-lib_"] {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:8px 8px 10px;
  gap:.4rem !important; }}
[class*="st-key-lib_"] img {{ border-radius:8px; aspect-ratio: 9 / 14; object-fit: cover; }}
.ar-noposter {{ aspect-ratio: 9 / 14; border-radius:8px; background:{SURFACE2}; display:flex; align-items:center;
  justify-content:center; }}
.ar-libt {{ font-size:.82rem; font-weight:500; color:{TEXT}; line-height:1.3; height:2.15rem; overflow:hidden;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
.ar-libs {{ font-size:.72rem; color:{MUTED}; margin-top:.25rem; padding-bottom:.35rem; line-height:1.3; }}
[class*="st-key-lib_"] .stButton button {{ min-height:2rem; font-size:.8rem; }}
.ar-kv {{ display:grid; grid-template-columns: 8rem 1fr; gap:.45rem .75rem; font-size:.86rem; }}
.ar-kv .k {{ color:{MUTED}; }} .ar-kv .v {{ color:{TEXT}; }}
</style>""", unsafe_allow_html=True)

st.markdown(f"""
<style>
/* round 3: fewer "AI app" tells. White primary, sentence-case headings, flat surfaces, accent only for state. */
.block-container {{ padding-top: .6rem; }}
.st-key-topbar {{ border-bottom: 1px solid {LINE}; padding-bottom: .7rem; margin-bottom: 1.3rem; }}
.ar-logo {{ font-size: 1.05rem; font-weight: 700; letter-spacing: -.02em; }}
.ar-meta {{ font-size: .8rem; }}
[data-testid="stButtonGroup"] button {{ border: none !important; background: transparent !important; border-radius: 8px !important;
  min-height: 2rem; padding: 0 .85rem; }}
[data-testid="stButtonGroup"] button p {{ color: {MUTED}; font-weight: 500; font-size: .9rem; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: {SURFACE2} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: {TEXT} !important; font-weight: 600; }}
[data-testid="stButtonGroup"] button:hover p {{ color: {TEXT}; }}
.ar-section {{ text-transform: none; letter-spacing: 0; font-size: .9rem; font-weight: 600; color: {TEXT};
  margin: .2rem 0 .5rem 0; }}
.st-key-panel {{ background: transparent; border: none; padding: 0; }}
.st-key-panel [data-testid="stVerticalBlock"] {{ gap: .7rem; }}
.st-key-stage {{ background: #111214; border: 1px solid {LINE}; border-radius: 14px; }}
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {{
  background: #F2F2EF !important; }}
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-primaryFormSubmit"] p {{
  color: #0D0E10 !important; }}
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: #FFFFFF !important; }}
[class*="st-key-card_"] {{ background: transparent; border: 1px solid transparent; padding: 0; gap: .45rem !important; }}
[class*="st-key-card_"] img {{ border-radius: 10px; border: 1px solid {LINE}; aspect-ratio: 4 / 5; }}
[class*="st-key-card_"]:hover img {{ border-color: #4A4D54; }}
[class*="st-key-card_"][class*="_on"] {{ border-color: transparent; box-shadow: none; }}
[class*="st-key-card_"][class*="_on"] img {{ border: 2px solid {TEXT}; }}
[class*="st-key-card_"] .stButton button {{ justify-content: flex-start; }}
[class*="st-key-card_"] .stButton button p {{ font-weight: 500; color: {MUTED}; }}
[class*="st-key-card_"][class*="_on"] .stButton button p {{ color: {TEXT}; font-weight: 600; }}
.ar-facts {{ justify-content: center; gap: .5rem; color: {MUTED}; font-size: .84rem; margin: 1.1rem 0 .8rem 0; }}
.ar-facts .sep {{ color: #4A4D54; }}
[data-testid="stExpander"] details {{ border-color: {LINE}; }}
[data-testid="stFileUploaderDropzone"] {{ border-style: solid; }}
</style>""", unsafe_allow_html=True)


# ---------------- helpers ----------------
def settings() -> Settings:
    return Settings.from_env()


def save_upload(f, allowed: set[str]) -> str:
    ext = Path(f.name).suffix.lower()
    if ext not in allowed:
        raise ValueError(f"{f.name}: unsupported file type {ext}")
    data = f.getvalue()
    if len(data) > MAX_UPLOAD_MB * 1_000_000:
        raise ValueError(f"{f.name} is larger than {MAX_UPLOAD_MB} MB")
    d = settings().outputs_dir / "_uploads" / secrets.token_hex(6)
    d.mkdir(parents=True, exist_ok=True)
    p = d / safe_filename(f.name)
    p.write_bytes(data)
    return str(p)


def start_job(fn) -> None:
    """Run the pipeline in a background thread; progress is read from state.json, never simulated."""
    holder: dict = {}

    def target():
        try:
            fn(holder)
        except Exception as e:  # noqa: BLE001 - the job's state.json records the failure
            holder["error"] = f"{type(e).__name__}: {e}"
    th = threading.Thread(target=target, daemon=True)
    th.start()
    for _ in range(100):  # wait until the job folder exists so we can follow it
        if "job_id" in holder or "error" in holder or not th.is_alive():
            break
        time.sleep(0.05)
    if "job_id" in holder:
        st.session_state["job_id"] = holder["job_id"]
        st.session_state["nav_to"] = "Create"
    if "error" in holder:
        st.session_state["start_error"] = holder["error"]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def voice_options() -> list[str]:
    from providers.tts import list_voices
    return [v["ShortName"] for v in list_voices("en-")]


def voice_label(v: str) -> str:
    if not v:
        return "Default voice"
    parts = v.replace("Neural", "").split("-")
    return f"{parts[-1]} ({'-'.join(parts[:2])})" if len(parts) >= 3 else v


def run_new(brief: Brief, mode: str, seed: int, reuse: bool = True):
    def fn(holder):
        from orchestrator import Pipeline
        s = settings()
        s.execution_mode = mode  # type: ignore[assignment]
        p = Pipeline(brief, settings=s, seed=seed, reuse_content=reuse)
        holder["job_id"] = p.job.id
        p.run()
    start_job(fn)


def run_rerender(job_id: str, style: dict):
    def fn(holder):
        from orchestrator import rerender
        holder["job_id"] = job_id
        rerender(job_id, style, settings=settings())
    start_job(fn)


def section(text: str) -> None:
    st.markdown(f'<div class="ar-section">{html.escape(text)}</div>', unsafe_allow_html=True)


def pill(status: str) -> str:
    text, kind = STATUS_TEXT.get(status or "", (status or "Unknown", "neutral"))
    return f'<span class="ar-pill {kind}">{html.escape(text)}</span>'


def read_state(job_id: str) -> dict | None:
    p = settings().outputs_dir / job_id / "state.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def when(ts: str | None) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%d %b, %H:%M") if ts else ""
    except ValueError:
        return ""


def short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


FIELD_NAMES = {"topic": "Prompt", "audience": "Audience", "tone": "Tone", "duration_s": "Length",
               "cta": "Call to action", "must_include": "Must mention", "must_avoid": "Avoid",
               "voice": "Voice", "source_text": "Pasted text", "language": "Language"}


def or_default(value: str, default: str, min_len: int = 2) -> str:
    """Blank or too-short optional fields fall back to their default instead of failing."""
    value = (value or "").strip()
    return value if len(value) >= min_len else default


def friendly_errors(err) -> list[str]:
    from pydantic import ValidationError
    if not isinstance(err, ValidationError):
        return [str(err)]
    out = []
    for e in err.errors():
        field = FIELD_NAMES.get(str(e["loc"][0]) if e["loc"] else "", "This form")
        kind, ctx = e["type"], e.get("ctx") or {}
        msg0 = str(e.get("msg", ""))
        if "duration_s must be between" in msg0:
            out.append("Length: full videos are 30-60 seconds. Turn on \"Quick test\" for shorter ones.")
        elif "dev-short videos must be at least" in msg0:
            out.append("Length: test videos must be at least 5 seconds.")
        elif field == "Prompt" and kind in ("string_too_short", "missing"):
            out.append("Prompt: describe what the video is about in a few words.")
        elif kind == "string_too_short":
            out.append(f"{field}: enter at least {ctx.get('min_length', 2)} characters.")
        elif kind == "string_too_long":
            out.append(f"{field}: shorten this to {ctx.get('max_length')} characters or fewer.")
        elif kind == "too_long":
            out.append(f"{field}: too many items (at most {ctx.get('max_length')}).")
        else:
            out.append(f"{field}: {str(e.get('msg', '')).removeprefix('Value error, ')}")
    return out


def _short_model(model: str) -> str:
    return model.split("/")[-1].split(":")[0]


# ---------------- top bar ----------------
s = settings()
if s.llm_provider == "gemini":
    provider_name, model_name, has_key = "Gemini", _short_model(s.gemini_model), bool(s.gemini_api_key)
else:
    provider_name, model_name, has_key = "OpenRouter", _short_model(s.openrouter_model), bool(s.openrouter_api_key)

if "nav_to" in st.session_state:  # programmatic navigation must happen before the widget is created
    st.session_state["view"] = st.session_state.pop("nav_to")
if "view" not in st.session_state:
    st.session_state["view"] = "Create"

with st.container(key="topbar"):
    t1, t2, t3 = st.columns([1.1, 4, 2.4], vertical_alignment="center")
    t1.markdown('<div class="ar-logo">AgentReel</div>', unsafe_allow_html=True)
    with t2:
        view = st.segmented_control("View", ["Create", "Library", "System"], key="view",
                                    label_visibility="collapsed") or "Create"
    t3.markdown(f'<div class="ar-meta">{provider_name} · {html.escape(model_name)}'
                f'{"" if has_key else " · no API key"}</div>', unsafe_allow_html=True)


# ---------------- right-hand stage: idle preview / progress / result ----------------
@st.fragment(run_every=2.0)
def progress_panel(job_id: str):
    state = read_state(job_id)
    if not state:
        st.markdown('<div class="ar-progress"><div class="now">Starting…</div></div>', unsafe_allow_html=True)
        return
    status = state.get("status")
    stages = state.get("stages", {})
    if status not in ("running", "created"):
        if st.session_state.get("_last_rendered") != (job_id, state.get("updated_at")):
            st.session_state["_last_rendered"] = (job_id, state.get("updated_at"))
            st.rerun()
        return
    done = sum(1 for k in STAGES if stages.get(k, {}).get("status") in ("done", "skipped"))
    cur = state.get("current_stage")
    rows = []
    for k in STAGES:
        info = stages.get(k, {})
        stt = info.get("status", "pending")
        cls = "running" if k == cur and stt == "running" else stt
        tries = f" · attempt {info['attempts']}" if info.get("attempts", 0) > 1 else ""
        rows.append(f'<div class="ar-stage {cls}"><span class="ar-dot {cls}"></span>'
                    f'{html.escape(STAGE_LABELS[k])}{tries}</div>')
    pct = int(100 * done / len(STAGES))
    st.markdown(f'<div class="ar-progress"><div class="now">{html.escape(STAGE_LABELS.get(cur, "Preparing"))}</div>'
                f'<div class="sub">Step {min(done + 1, len(STAGES))} of {len(STAGES)}. You can leave this open.</div>'
                f'<div class="ar-bar"><div style="width:{pct}%"></div></div>{"".join(rows)}</div>',
                unsafe_allow_html=True)


def idle_stage(mode: str) -> None:
    p = UI_ASSETS / f"preview_{mode}.mp4"
    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
    if p.exists():
        st.video(str(p), autoplay=True, loop=True, muted=True)
    st.markdown(f'<div class="ar-example">Example of the {html.escape(MODES[mode][0])} style</div>',
                unsafe_allow_html=True)


def job_stage(job_id: str) -> None:
    state = read_state(job_id) or {}
    status = state.get("status")
    mode_name = MODES.get(state.get("mode"), (state.get("mode") or "",))[0]
    h1, h2 = st.columns([5, 1], vertical_alignment="top")
    h1.markdown(f'<div class="ar-stagehead"><div><div class="t">{html.escape(short(state.get("topic") or job_id, 120))}'
                f'</div><div class="s">{html.escape(mode_name)} · {when(state.get("created_at"))}</div></div></div>',
                unsafe_allow_html=True)
    h2.markdown(f'<div style="text-align:right">{pill(status)}</div>', unsafe_allow_html=True)
    if status in ("running", "created", None):
        progress_panel(job_id)
        return
    if status == "failed":
        st.error(f"The video could not be made. {state.get('error', '')}")
    final = s.outputs_dir / job_id / "final.mp4"
    if final.exists():
        st.video(str(final))


def job_details(job_id: str) -> None:
    """Actions and details under the stage once a video is finished."""
    state = read_state(job_id) or {}
    if state.get("status") in ("running", "created", None):
        return
    job_dir = s.outputs_dir / job_id
    final, srt = job_dir / "final.mp4", job_dir / "captions.srt"
    qa_p = job_dir / "qa_report.json"
    qa = json.loads(qa_p.read_text(encoding="utf-8")) if qa_p.exists() else None
    facts = []
    if qa and qa.get("output", {}).get("duration_s"):
        facts.append(f"{qa['output']['duration_s']:.0f} s")
    if state.get("is_test_render"):
        facts.append("Quick test")
    if qa:
        facts.append("All checks passed" if qa["technical_pass"] else "Some checks failed")
        facts.append({"approved": "AI review: approved", "needs_changes": "AI review: changes suggested",
                      "not_reviewed": "Not AI-reviewed"}.get(qa["semantic_status"], ""))
    facts.append(f"{state.get('llm_calls', 0)} AI calls")
    st.markdown('<div class="ar-facts">' + '<span class="sep">·</span>'.join(
        f'<span>{html.escape(f)}</span>' for f in facts if f) + "</div>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    if final.exists():
        b1.download_button("Download MP4", final.read_bytes(), file_name=f"{job_id}.mp4", mime="video/mp4",
                           type="primary", use_container_width=True)
    if srt.exists():
        b2.download_button("Captions (SRT)", srt.read_bytes(), file_name=f"{job_id}.srt", use_container_width=True)
    if b3.button("Close", use_container_width=True):
        st.session_state.pop("job_id", None)
        st.rerun()
    if qa:
        for c in [c for c in qa["checks"] if not c["passed"] and c["severity"] == "error"]:
            st.error(f"{c['name'].replace('_', ' ').capitalize()}: {c['detail']}")

    st.write("")
    tabs = st.tabs(["Script", "Restyle", "New version", "Sources", "Checks", "Details"])
    with tabs[0]:
        p = job_dir / "script.json"
        if p.exists():
            sc = json.loads(p.read_text(encoding="utf-8"))
            for seg in sc.get("segments", []):
                st.markdown(f'<div style="padding:.35rem 0;border-bottom:1px solid {LINE};font-size:.92rem">'
                            f'{html.escape(seg["text"])}</div>', unsafe_allow_html=True)
    with tabs[1]:
        st.markdown('<div class="ar-caption">New caption look, same script and narration.</div>',
                    unsafe_allow_html=True)
        with st.form(f"restyle_{job_id}", border=False):
            r1, r2, r3 = st.columns(3)
            color = r1.color_picker("Text", "#FFFFFF")
            hl = r2.color_picker("Highlight", "#FFE135")
            outline = r3.color_picker("Outline", "#000000")
            r4, r5, r6 = st.columns(3)
            size = r4.slider("Size", 48, 140, 84)
            pos = r5.selectbox("Position", ["center", "lower", "upper"], format_func=str.capitalize)
            anim = r6.selectbox("Animation", ["pop", "slide", "fade", "none"], format_func=str.capitalize)
            r7, r8 = st.columns(2)
            emph = r7.slider("Keyword emphasis", 0.0, 1.0, 0.6)
            motion_r = r8.selectbox("Camera motion", list(MOTION), format_func=MOTION.get, key=f"mot_{job_id}")
            r9, r10 = st.columns(2)
            upper = r9.toggle("Uppercase", True)
            progress = r10.toggle("Progress bar", True)
            if st.form_submit_button("Re-render", type="primary"):
                run_rerender(job_id, {"caption": {"color": color, "highlightColor": hl, "outlineColor": outline,
                                                  "fontSize": size, "position": pos, "animation": anim,
                                                  "emphasis": emph, "uppercase": upper},
                                      "motion": motion_r, "show_progress": progress})
                st.rerun()
    with tabs[2]:
        st.markdown('<div class="ar-caption">Same script and sources in another style or voice. Quick, because '
                    'only the video is made again.</div>', unsafe_allow_html=True)
        bp = job_dir / "brief.json"
        if bp.exists():
            base = Brief.model_validate(json.loads(bp.read_text(encoding="utf-8")))
            with st.form(f"version_{job_id}", border=False):
                n1, n2 = st.columns(2)
                new_mode = n1.selectbox("Style", list(MODES), index=list(MODES).index(base.mode),
                                        format_func=lambda m: MODES[m][0])
                opts = [""] + voice_options()
                new_voice = n2.selectbox("Voice", opts, index=opts.index(base.voice) if base.voice in opts else 0,
                                         format_func=voice_label)
                if st.form_submit_button("Make this version", type="primary"):
                    run_new(base.model_copy(update={"mode": new_mode, "voice": new_voice}),
                            st.session_state.get("exec_mode", s.execution_mode), int(state.get("seed", 42)),
                            reuse=True)
                    st.rerun()
    with tabs[3]:
        p = job_dir / "facts.json"
        if p.exists():
            fj = json.loads(p.read_text(encoding="utf-8"))
            for lim in fj.get("limitations", []):
                st.info(lim)
            rows = [{"Fact": f.get("claim"), "Status": f.get("status", "").replace("_", " "),
                     "Source": f.get("source") or "", "Page": f.get("page") or ""} for f in fj.get("facts", [])]
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.caption("No source facts were used.")
    with tabs[4]:
        if qa:
            st.dataframe([{"Check": c["name"].replace("_", " "), "Result": "Pass" if c["passed"] else
                           ("Fail" if c["severity"] == "error" else "Note"), "Detail": c["detail"]}
                          for c in qa["checks"]], use_container_width=True, hide_index=True)
        for n in state.get("notes") or []:
            st.caption(n)
    with tabs[5]:
        with st.expander("Storyboard"):
            p = job_dir / "storyboard.json"
            if p.exists():
                st.json(json.loads(p.read_text(encoding="utf-8")), expanded=False)
        with st.expander("Assets and licences"):
            p = job_dir / "assets" / "manifest.csv"
            if p.exists():
                st.dataframe(list(csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))),
                             use_container_width=True, hide_index=True)
        with st.expander("AI usage and cost"):
            p = job_dir / "logs" / "cost_report.csv"
            rows = list(csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))) if p.exists() else []
            st.caption(f"{state.get('llm_calls', 0)} calls · ${state.get('llm_cost_usd', 0):.4f}")
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
        with st.expander("Run log"):
            p = job_dir / "logs" / "run_log.jsonl"
            if p.exists():
                lines = p.read_text(encoding="utf-8").splitlines()
                st.dataframe([json.loads(x) for x in lines[-300:]], use_container_width=True, hide_index=True)
        st.caption(f"Folder: {job_dir}")


# ---------------- create view ----------------
def style_cards() -> str:
    if "style" not in st.session_state:
        st.session_state["style"] = "og"
    cols = st.columns(3, gap="small")
    for col, (key, (name, _)) in zip(cols, MODES.items()):
        on = st.session_state["style"] == key
        with col:
            with st.container(key=f"card_{key}{'_on' if on else ''}"):
                thumb = UI_ASSETS / f"thumb_{key}.jpg"
                if thumb.exists():
                    st.image(str(thumb), use_container_width=True)
                if st.button(name, key=f"pick_{key}", use_container_width=True):
                    st.session_state["style"] = key
                    st.rerun()
    return st.session_state["style"]


def create_view() -> None:
    if st.session_state.get("start_error"):
        st.error(st.session_state.pop("start_error"))
    left, right = st.columns([5, 7], gap="large")
    with left:
        with st.container(key="panel"):
            section("Style")
            mode = style_cards()
            ready = True
            if mode != "og":
                usable = [c for c in library_status(deep=False)[mode] if c.usable]
                ready = bool(usable)
                if not ready:
                    st.error(f"No {MODES[mode][0]} footage is set up. See the System tab.")
            st.markdown(f'<div class="ar-caption">{html.escape(MODES[mode][1])}</div>', unsafe_allow_html=True)
            st.write("")

            section("Prompt")
            topic = st.text_area("Prompt", placeholder="What should the video be about?\n\nFor example: Explain how "
                                 "vaccines train the immune system, for teenagers.", max_chars=1000, height=140,
                                 label_visibility="collapsed")
            sources = st.file_uploader("Attach documents", type=["pdf", "docx", "txt", "md"],
                                       accept_multiple_files=True,
                                       help="Facts in the video are checked against these.")

            section("Voice and length")
            v1, v2 = st.columns([3, 2])
            voice = v1.selectbox("Voice", [""] + voice_options(), format_func=voice_label)
            fmt = v2.selectbox("Format", list(FORMATS), format_func=FORMATS.get)
            dev_short = st.toggle("Quick test (short, low resolution)")
            l1, l2 = st.columns([3, 2]) if mode != "og" else (st.container(), None)
            duration = l1.slider("Length (seconds)", 5 if dev_short else PROD_MIN_S,
                                 30 if dev_short else PROD_MAX_S, 12 if dev_short else 45)
            motion = "auto"
            if mode != "og":
                motion = l2.selectbox("Camera motion", list(MOTION), format_func=MOTION.get,
                                      help="Auto: the AI decides which lines get a zoom and shake.")

            with st.expander("More settings"):
                a1, a2 = st.columns(2)
                audience = a1.text_input("Audience", placeholder="General audience")
                tone = a2.text_input("Tone", placeholder="Engaging, clear")
                content_type = st.selectbox("Type", list(CONTENT_TYPES), format_func=CONTENT_TYPES.get)
                must_include = st.text_area("Must mention", height=70, placeholder="One point per line")
                must_avoid = st.text_area("Avoid", height=70, placeholder="One item per line")
                cta = st.text_input("Call to action", placeholder="For example: Follow for part two")
                source_text = st.text_area("Paste source text", height=90)
                o1, o2 = st.columns(2)
                language = o1.text_input("Narration language", "English")
                subtitle_language = o2.text_input("Caption language", "English")
                narration = st.file_uploader("Your own narration", type=["mp3", "wav", "m4a", "aac", "ogg"])
                music = st.file_uploader("Background music (you need the rights)",
                                         type=["mp3", "wav", "m4a", "aac", "ogg", "flac"])
                fresh = st.toggle("Write a fresh script",
                                  help="Normally a script is reused when the same prompt and documents were used "
                                       "before.")
                e1, e2 = st.columns([3, 2])
                exec_mode = e1.selectbox("AI usage", list(EXEC_MODES), format_func=EXEC_MODES.get,
                                         index=list(EXEC_MODES).index(s.execution_mode), key="exec_mode")
                seed = e2.number_input("Seed", value=42, step=1)

            st.write("")
            if st.button("Generate", type="primary", use_container_width=True, disabled=not ready):
                try:
                    brief = Brief.model_validate({
                        "topic": topic, "audience": or_default(audience, "General audience"),
                        "tone": or_default(tone, "engaging, clear"), "content_type": content_type, "mode": mode,
                        "duration_s": duration, "format": fmt, "language": or_default(language, "English"),
                        "subtitle_language": or_default(subtitle_language, "English"),
                        "must_include": [x for x in must_include.splitlines() if x.strip()],
                        "must_avoid": [x for x in must_avoid.splitlines() if x.strip()], "cta": cta,
                        "source_files": [save_upload(f, SOURCE_EXT) for f in sources or []],
                        "source_text": source_text,
                        "narration_audio": save_upload(narration, AUDIO_EXT) if narration else "",
                        "music": save_upload(music, AUDIO_EXT) if music else "", "dev_short": dev_short,
                        "voice": voice, "motion": motion})
                    run_new(brief, exec_mode, int(seed), reuse=not fresh)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error("\n".join(f"- {m}" for m in friendly_errors(e)))
            if not has_key and exec_mode != "LOCAL_ONLY":
                st.markdown('<div class="ar-caption">No API key for the AI provider; simple templates will be '
                            'used.</div>', unsafe_allow_html=True)

    with right:
        job_id = st.session_state.get("job_id")
        with st.container(key="stage"):
            if job_id:
                job_stage(job_id)
            else:
                idle_stage(mode)
        if job_id:
            job_details(job_id)


# ---------------- library view ----------------
def poster(job_dir: Path) -> Path | None:
    """A cached poster frame for the library grid (one ffmpeg call per video, done once)."""
    out = job_dir / "render" / "poster.jpg"
    final = job_dir / "final.mp4"
    if out.exists() or not final.exists():
        return out if out.exists() else None
    import subprocess
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = tool_path("ffmpeg")
    if ff:
        subprocess.run([ff, "-v", "error", "-y", "-ss", "2", "-i", str(final), "-vf", "scale=320:-2", "-frames:v", "1",
                        "-q:v", "4", str(out)], capture_output=True, timeout=60)
    return out if out.exists() else None


def library_view() -> None:
    jobs = [j for j in list_jobs(s.outputs_dir) if j.get("job_id")]
    jobs.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    jobs = jobs[:48]
    if not jobs:
        st.caption("No videos yet.")
        return
    per_row = 6
    for start in range(0, len(jobs), per_row):
        cols = st.columns(per_row, gap="medium")
        for col, j in zip(cols, jobs[start:start + per_row]):
            jid = j["job_id"]
            with col:
                with st.container(key=f"lib_{jid}"):
                    img = poster(s.outputs_dir / jid)
                    if img:
                        st.image(str(img), use_container_width=True)
                    else:
                        st.markdown(f'<div class="ar-noposter">{pill(j.get("status"))}</div>',
                                    unsafe_allow_html=True)
                    mode_name = MODES.get(j.get("mode"), (j.get("mode") or "",))[0]
                    st.markdown(f'<div class="ar-libt">{html.escape(short(j.get("topic") or jid, 70))}</div>'
                                f'<div class="ar-libs">{html.escape(mode_name)} · {when(j.get("created_at"))}</div>',
                                unsafe_allow_html=True)
                    if st.button("Open", key=f"open_{jid}", use_container_width=True):
                        st.session_state["job_id"] = jid
                        st.session_state["nav_to"] = "Create"
                        st.rerun()

# ---------------- system view ----------------
def kv(rows) -> None:
    st.markdown('<div class="ar-kv">' + "".join(
        f'<div class="k">{html.escape(str(k))}</div><div class="v">{html.escape(str(v))}</div>' for k, v in rows)
        + "</div>", unsafe_allow_html=True)


def system_view() -> None:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(key="panel"):
            section("AI provider")
            if s.llm_provider == "gemini":
                kv([("Provider", "Gemini"), ("Model", s.gemini_model),
                    ("Fallbacks", ", ".join(s.gemini_fallback_models) or "None"),
                    ("API key", "Set" if s.gemini_api_key else "Missing"),
                    ("Request gap", f"{s.gemini_min_interval_s:g} s")])
            else:
                kv([("Provider", "OpenRouter"), ("Model", s.openrouter_model),
                    ("Fallbacks", ", ".join(s.openrouter_fallback_models) or "None"),
                    ("API key", "Set" if s.openrouter_api_key else "Missing"),
                    ("Paid models", "Allowed" if s.allow_paid_models else "Blocked"),
                    ("Spend limit", f"${s.max_api_spend_usd:g}")])
            st.markdown('<div class="ar-caption">Switch with <code>streamlit run app.py -- --provider gemini</code> '
                        '(or openrouter).</div>', unsafe_allow_html=True)
            st.write("")
            section("Tools")
            kv([(n, "Installed" if ok else "Missing") for n, ok in
                [("FFmpeg", tool_path("ffmpeg")), ("FFprobe", tool_path("ffprobe")), ("Node.js", tool_path("node")),
                 ("Remotion", remotion_runner.is_available()), ("Manim", manim_runner.is_available())]])
    with c2:
        section("Gameplay footage")
        for game, clips in library_status(deep=False).items():
            if game not in MODES:
                continue
            st.markdown(f"**{MODES[game][0]}**")
            if not clips:
                st.caption("No clips registered.")
            for c in clips:
                r = c.as_row()
                st.markdown(f'<div class="ar-row"><div><div class="t">{html.escape(r["asset"])}</div>'
                            f'<div class="s">{r["duration_s"]} s · {r["resolution"]} · '
                            f'{"ready" if r["usable"] else "not usable"} · permission '
                            f'{html.escape(r["review_status"].replace("_", " "))}</div></div></div>',
                            unsafe_allow_html=True)
        st.markdown('<div class="ar-caption">Clips marked "needs review" are not confirmed as licensed for reuse. '
                    'Replace them with your own recordings before publishing.</div>', unsafe_allow_html=True)


if view == "Library":
    library_view()
elif view == "System":
    system_view()
else:
    create_view()
