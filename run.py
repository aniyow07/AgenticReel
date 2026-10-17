"""AgentReel command line.

Examples:
  python run.py --brief briefs/examples/procrastination.yaml --seed 42
  python run.py --brief briefs/examples/green_hydrogen.yaml --local-only --dev-short
  python run.py --topic "Why do cats purr?" --mode subway --duration 40
  python run.py --resume <JOB_ID>
  python run.py --rerender <JOB_ID> --caption-color "#FFFFFF" --highlight-color "#FF3D7F"
  python run.py --status            # toolchain + gameplay readiness
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def status() -> int:
    from core.config import Settings
    from core.gameplay import library_status
    from rendering import manim_runner, remotion_runner
    from rendering.media_utils import tool_path

    s = Settings.from_env()
    print("Toolchain:")
    for t in ("ffmpeg", "ffprobe", "node"):
        print(f"  {t:10s} {'ok' if tool_path(t) else 'MISSING'}")
    print(f"  remotion   {'ok' if remotion_runner.is_available() else 'MISSING (npm install in remotion/)'}")
    print(f"  manim      {'ok' if manim_runner.is_available() else 'MISSING'}")
    print(f"LLM: mode={s.execution_mode} model={s.openrouter_model} fallbacks={s.openrouter_fallback_models} "
          f"key={'set' if s.openrouter_api_key else 'not set'} paid={'allowed' if s.allow_paid_models else 'blocked'}")
    print("Gameplay:")
    for game, clips in library_status(deep=True).items():
        usable = [c for c in clips if c.usable]
        print(f"  {game:9s} {len(usable)} usable clip(s)" + ("" if usable else
              f"  -> run: python scripts/setup_gameplay_assets.py --game {game}"))
        for c in clips:
            print(f"    - {c.record.asset_id}: {c.duration_s}s {c.width}x{c.height} review={c.record.review_status}"
                  f"{' PROBLEMS: ' + '; '.join(c.problems) if c.problems else ''}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="AgentReel video generator",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--brief", help="YAML brief file")
    ap.add_argument("--topic", help="topic for a quick brief without a YAML file")
    ap.add_argument("--audience")
    ap.add_argument("--content-type")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--mode", choices=["og", "minecraft", "subway"])
    ap.add_argument("--format", choices=["video_9x16", "video_16x9"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--local-only", action="store_true", help="make no LLM API calls")
    ap.add_argument("--ai-required", action="store_true", help="fail if the LLM is unavailable")
    ap.add_argument("--dev-short", action="store_true", help="short, small test render (labelled as a test)")
    ap.add_argument("--resume", metavar="JOB_ID")
    ap.add_argument("--rerender", metavar="JOB_ID", help="re-render an existing job with new style options")
    ap.add_argument("--caption-color")
    ap.add_argument("--highlight-color")
    ap.add_argument("--caption-size", type=float)
    ap.add_argument("--caption-position", choices=["upper", "center", "lower"])
    ap.add_argument("--output-dir", help="where job folders are written (default ./outputs)")
    ap.add_argument("--voice", help="Edge TTS voice, e.g. en-US-GuyNeural (see --list-voices)")
    ap.add_argument("--provider", choices=["openrouter", "gemini"],
                    help="LLM provider for this run (default: LLM_PROVIDER in .env, else openrouter)")
    ap.add_argument("--gemini-interval", type=float, metavar="SECONDS",
                    help="minimum seconds between Gemini requests (default GEMINI_MIN_INTERVAL_S or 6)")
    ap.add_argument("--motion", choices=["auto", "subtle", "strong", "off"],
                    help="brainrot camera motion; auto lets the AI pick per line (default)")
    ap.add_argument("--list-voices", action="store_true", help="print available Edge TTS voices and exit")
    ap.add_argument("--fresh-script", action="store_true",
                    help="write a new plan/script even if the same brief + sources were already used")
    ap.add_argument("--script-json", help="use this validated script.json instead of the Scriptwriter")
    ap.add_argument("--storyboard-json", help="use this storyboard instead of the Storyboarder")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.provider:
        os.environ["LLM_PROVIDER"] = a.provider
    if a.gemini_interval is not None:
        os.environ["GEMINI_MIN_INTERVAL_S"] = str(a.gemini_interval)
    if a.output_dir:
        os.environ["AGENTREEL_OUTPUT_DIR"] = str(Path(a.output_dir).resolve())
    if a.local_only:
        os.environ["AGENTREEL_EXECUTION_MODE"] = "LOCAL_ONLY"
    elif a.ai_required:
        os.environ["AGENTREEL_EXECUTION_MODE"] = "AI_REQUIRED"

    if a.list_voices:
        from providers.tts import list_voices
        for v in list_voices():
            print(f"{v['ShortName']:38s} {v.get('Gender', ''):7s} {v.get('Locale', '')}")
        return 0
    if a.status:
        return status()

    from pydantic import ValidationError

    from core.config import Settings
    from orchestrator import Pipeline, rerender
    from schemas.brief import Brief, load_brief

    settings = Settings.from_env()
    try:
        if a.rerender:
            cap = {k: v for k, v in {"color": a.caption_color, "highlightColor": a.highlight_color,
                                     "fontSize": a.caption_size, "position": a.caption_position}.items() if v}
            report = rerender(a.rerender, {"caption": cap, **({"motion": a.motion} if a.motion else {})},
                              settings=settings)
            job_dir = settings.outputs_dir / a.rerender
        elif a.resume:
            p = Pipeline(job_id=a.resume, settings=settings, seed=a.seed)
            report = p.run()
            job_dir = p.job.dir
        else:
            overrides = {"motion": a.motion, "voice": a.voice, "mode": a.mode, "format": a.format, "duration_s": a.duration, "audience": a.audience,
                         "content_type": a.content_type}
            if a.dev_short:
                overrides["dev_short"] = True
                if a.duration is None:
                    overrides["duration_s"] = 12
            if a.brief:
                brief = load_brief(a.brief, **overrides)
            elif a.topic:
                brief = Brief.model_validate({"topic": a.topic, **{k: v for k, v in overrides.items() if v is not None}})
            else:
                ap.error("give --brief, --topic, --resume or --rerender")
            p = Pipeline(brief, settings=settings, seed=a.seed, preset_script=a.script_json,
                         preset_storyboard=a.storyboard_json, reuse_content=not a.fresh_script,
                         on_update=lambda j: print(f"  [{j.state.get('current_stage') or j.state['status']}]",
                                                   flush=True))
            print(f"Job {p.job.id} -> {p.job.dir}")
            report = p.run()
            job_dir = p.job.dir
    except ValidationError as e:
        print(f"Invalid brief:\n{e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print()
    print(f"Technical QA: {'PASS' if report.technical_pass else 'FAIL'} | semantic review: {report.semantic_status}"
          f" | repairs: {report.repairs_attempted}{' | TEST RENDER' if report.is_test_render else ''}")
    for c in report.checks:
        if not c.passed:
            print(f"  [{c.severity}] {c.name}: {c.detail}")
    print(f"Output: {job_dir / 'final.mp4'}")
    print(json.dumps(report.output, indent=2))
    return 0 if report.technical_pass else 3


if __name__ == "__main__":
    sys.exit(main())

