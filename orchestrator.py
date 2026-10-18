"""Top-level pipeline: runs the seven agents, caches stages, and drives the repair loop.

Stages (see core/jobs.STAGES): planning -> research -> scripting -> storyboarding -> assets -> tts ->
manim -> editing -> remotion_render -> ffmpeg -> qa. Each stage records a fingerprint of its inputs;
on resume a stage is skipped only if it finished, its artifacts exist and its inputs are unchanged.
"""
from __future__ import annotations

import json
import shutil
import traceback
from pathlib import Path
from typing import Callable

import yaml

from agents import asset_generator, critic, editor, planner, researcher, scriptwriter, storyboarder
from agents.base import AgentContext, AgentFailure
from core import gameplay
from core.config import Settings
from core.content_cache import ContentCache, content_key
from core.jobs import STAGES, Job, fingerprint, new_job_id, safe_filename
from core.themes import manim_palette
from providers.openrouter import OpenRouterClient
from rendering import manim_runner
from rendering.media_utils import probe
from schemas.artifacts import AssetManifest, Facts, Plan, QAReport, Script, Storyboard
from schemas.brief import Brief
from schemas.render_props import RenderProps

ROUTE_ORDER = {s: i for i, s in enumerate(STAGES)}


class PipelineError(RuntimeError):
    pass


def make_llm(settings: Settings, job: Job):
    """The LLM client for the selected provider (LLM_PROVIDER / --provider): OpenRouter or Gemini."""
    if settings.execution_mode == "LOCAL_ONLY":
        return None
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            if settings.execution_mode == "AI_REQUIRED":
                raise PipelineError("AI_REQUIRED mode with provider gemini needs GEMINI_API_KEY")
            job.log.log("planning", "gemini", "unavailable", reason="GEMINI_API_KEY is not set; local fallback")
            return None
        from providers.gemini import GeminiClient
        return GeminiClient(settings, logger=job.log)
    if not settings.openrouter_api_key:
        if settings.execution_mode == "AI_REQUIRED":
            raise PipelineError("AI_REQUIRED mode needs OPENROUTER_API_KEY")
        return None
    return OpenRouterClient(settings, logger=job.log)

def import_inputs(job: Job, brief: Brief) -> Brief:
    """Copy source files / narration / music into the job so the job is self-contained."""
    inputs = job.dir / "inputs"
    inputs.mkdir(exist_ok=True)
    limit = 50_000_000

    def bring(p: str) -> str:
        if not p:
            return p
        src = Path(p)
        if not src.is_file():
            raise PipelineError(f"input file not found: {src.name}")
        if src.stat().st_size > limit:
            raise PipelineError(f"{src.name} exceeds the 50 MB upload limit")
        dst = inputs / safe_filename(src.name)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return str(dst)

    return brief.model_copy(update={"source_files": [bring(f) for f in brief.source_files],
                                    "narration_audio": bring(brief.narration_audio), "music": bring(brief.music)})


class Pipeline:
    def __init__(self, brief: Brief | None = None, settings: Settings | None = None, job_id: str | None = None,
                 seed: int = 42, on_update: Callable[[Job], None] | None = None, llm: OpenRouterClient | None = None,
                 preset_script: str | Path | None = None, preset_storyboard: str | Path | None = None,
                 reuse_content: bool = True):
        self.settings = settings or Settings.from_env()
        root = self.settings.outputs_dir
        root.mkdir(parents=True, exist_ok=True)
        if job_id:  # resume
            self.job = Job(root, job_id)
            if not self.job.exists("brief.json"):
                raise PipelineError(f"job {job_id} has no brief.json")
            self.brief = Brief.model_validate(self.job.read_json("brief.json"))
            seed = self.job.state.get("seed", seed)
        else:
            if brief is None:
                raise PipelineError("a brief is required for a new job")
            self.job = Job(root, new_job_id(brief.id or brief.mode))
            self.brief = import_inputs(self.job, brief)
            self.job.write_json("brief.json", self.brief)
            (self.job.dir / "brief.yaml").write_text(yaml.safe_dump(self.brief.model_dump(), sort_keys=False,
                                                                    allow_unicode=True), encoding="utf-8")
        for name, src in (("preset_script.json", preset_script), ("preset_storyboard.json", preset_storyboard)):
            if src:  # user-supplied artifacts replace the LLM/local stage; they are still validated
                data = json.loads(Path(src).read_text(encoding="utf-8-sig"))
                self.job.write_json(f"inputs/{name}", data)
                self.job.log.intervention(name.split("_")[1].split(".")[0], f"user supplied {name}", "preset artifact")
        self.seed = seed
        self.on_update = on_update
        # Same brief + same source files -> reuse plan/research/script/storyboard from an earlier job.
        self.reuse_content = self.job.state.get("reuse_content", reuse_content) if job_id else reuse_content
        self.job.set(reuse_content=self.reuse_content)
        # different providers (and local templates) keep separate caches so their scripts can be compared
        engine = "local" if self.settings.execution_mode == "LOCAL_ONLY" else self.settings.llm_provider
        self.cache = ContentCache(root, f"{content_key(self.brief)}-{engine}")
        self.job.set(seed=seed, mode=self.brief.mode, topic=self.brief.topic, config=self.settings.public_dict(),
                     llm_provider=self.settings.llm_provider,
                     is_test_render=self.brief.dev_short)
        self.ctx = AgentContext(job=self.job, brief=self.brief, settings=self.settings,
                                llm=llm if llm is not None else make_llm(self.settings, self.job), seed=seed)

    # ---------- helpers ----------
    def _notify(self):
        if self.on_update:
            try:
                self.on_update(self.job)
            except Exception:  # noqa: BLE001 - UI callbacks must never break the pipeline
                pass

    def _stage(self, name: str, fp: str, artifacts: list[str], fn, load):
        if self.job.cached(name, fp):
            self.job.log.log(name, "cache", "reused", fingerprint=fp)
            return load()
        self.job.stage_start(name)
        self._notify()
        try:
            result = fn()
        except Exception as e:
            self.job.stage_fail(name, f"{type(e).__name__}: {e}")
            self.job.log.log(name, "pipeline", "failed", error=str(e)[:2000], trace=traceback.format_exc()[-2000:])
            self._notify()
            raise
        self.job.stage_done(name, fp=fp, artifacts=artifacts)
        self._notify()
        return result

    def _from_cache(self, name: str, stage: str) -> dict | None:
        if not self.reuse_content:
            return None
        hit = self.cache.get(name)
        if not hit or hit.get("job_id") == self.job.id:
            return None
        self.job.log.log(stage, "content_cache", "reused", source_job=hit.get("job_id"), cache_key=self.cache.key,
                         note="same brief and source files as an earlier job")
        self.ctx.notes.append(f"{stage}: reused from job {hit.get('job_id')} (same brief and sources)")
        return hit["data"]

    # ---------- stages ----------
    def plan(self) -> Plan:
        fp = fingerprint(self.brief, self.settings.execution_mode, planner.PROMPT_VERSION)

        def fn():
            cached = self._from_cache("plan", "planning")
            if cached:
                cached = {**cached, "mode": self.brief.mode}
                if self.brief.mode != "og":
                    cached["manim_scenes"] = []
                p = Plan.model_validate(cached)
            else:
                p = planner.run(self.ctx)
            self.cache.put("plan", p.model_dump(mode="json"), self.job.id)
            self.job.write_json("plan.json", p)
            self.job.log.log("planning", "planner", "ok", origin=p.origin, output="plan.json")
            return p
        return self._stage("planning", fp, ["plan.json"], fn, lambda: self.job.read_json("plan.json", Plan))

    def research(self, plan: Plan) -> Facts:
        files = [(f, Path(f).stat().st_size if Path(f).exists() else 0) for f in self.brief.source_files]
        fp = fingerprint(plan, files, self.brief.source_text, researcher.PROMPT_VERSION)

        def fn():
            cached = self._from_cache("facts", "research")
            f = Facts.model_validate(cached) if cached else researcher.run(self.ctx, plan)
            if cached and self.brief.source_files:  # the retrieval index is used for on-screen text grounding
                researcher.ingest_index(self.ctx)
            self.cache.put("facts", f.model_dump(mode="json"), self.job.id)
            self.job.write_json("facts.json", f)
            self.job.log.log("research", "researcher", "ok", origin=f.origin, facts=len(f.facts),
                             supported=len(f.supported()), limitations=f.limitations, output="facts.json")
            return f
        return self._stage("research", fp, ["facts.json"], fn, lambda: self.job.read_json("facts.json", Facts))

    def script(self, plan: Plan, facts: Facts, feedback: list[str] | None = None) -> Script:
        preset = self.job.path("inputs/preset_script.json")
        fp = fingerprint(plan, facts, feedback or [], scriptwriter.PROMPT_VERSION,
                         preset.read_text(encoding="utf-8") if preset.exists() else None)

        def fn():
            if preset.exists():
                s = Script.model_validate({**json.loads(preset.read_text(encoding="utf-8")), "origin": "user"})
                issues = scriptwriter.check_script(s, facts, self.ctx)
                if issues:
                    self.job.log.log("scripting", "validator", "issues", issues=issues, note="user-supplied script")
            else:
                cached = None if feedback else self._from_cache("script", "scripting")
                s = Script.model_validate(cached) if cached else scriptwriter.run(self.ctx, plan, facts, feedback)
                self.cache.put("script", s.model_dump(mode="json"), self.job.id)
            self.job.write_json("script.json", s)
            self.job.write_text("script.md", s.to_markdown())
            self.job.log.log("scripting", "scriptwriter", "ok", origin=s.origin, words=s.word_count,
                             segments=len(s.segments), output="script.json")
            return s
        return self._stage("scripting", fp, ["script.json", "script.md"], fn,
                           lambda: self.job.read_json("script.json", Script))

    def storyboard(self, plan: Plan, script: Script, facts: Facts) -> Storyboard:
        preset = self.job.path("inputs/preset_storyboard.json")
        fp = fingerprint(plan, script, facts, storyboarder.PROMPT_VERSION,
                         preset.read_text(encoding="utf-8") if preset.exists() else None)

        def fn():
            if preset.exists():
                sb = storyboarder.from_user(self.ctx, json.loads(preset.read_text(encoding="utf-8")), script, facts)
            else:
                name = f"storyboard_{self.brief.mode}"
                cached = self._from_cache(name, "storyboarding")
                if cached and cached.get("script_fp") == fingerprint(script):
                    sb = Storyboard.model_validate(cached["storyboard"])
                else:
                    sb = storyboarder.run(self.ctx, plan, script, facts)
                self.cache.put(name, {"script_fp": fingerprint(script), "storyboard": sb.model_dump(mode="json")},
                               self.job.id)
            self.job.write_json("storyboard.json", sb)
            self.job.log.log("storyboarding", "storyboarder", "ok", origin=sb.origin, scenes=len(sb.scenes),
                             output="storyboard.json")
            return sb
        return self._stage("storyboarding", fp, ["storyboard.json"], fn,
                           lambda: self.job.read_json("storyboard.json", Storyboard))

    def assets_and_audio(self, script: Script, storyboard: Storyboard) -> AssetManifest:
        prof = editor.output_profile(self.ctx)
        # TTS first: everything else is timed from the measured narration.
        tts_fp = fingerprint(script, self.settings.tts_provider, self.ctx.voice, self.ctx.base_rate,
                             self.brief.narration_audio)

        def tts_fn():
            segs = asset_generator.synthesize_segments(self.ctx, script)
            fit = self._fit_rate(segs)
            if fit:  # nudge the pace (at most 15 points either way) so the narration fits the allowed length
                self.ctx.rate_override, why = fit
                self.job.log.log("tts", "pacing", "adjusted", rate=self.ctx.rate_override, reason=why)
                self.ctx.notes.append(f"Narration pace set to {self.ctx.rate_override}: {why}.")
                segs = asset_generator.synthesize_segments(self.ctx, script)
            narration = asset_generator.assemble_narration(self.ctx, segs, editor.SEGMENT_GAP_S)
            self.job.write_json("assets/tts.json", {"segments": [s.model_dump() for s in segs],
                                                    "narration": str(narration)})
            return segs, narration

        def tts_load():
            d = self.job.read_json("assets/tts.json")
            from schemas.artifacts import SegmentAudio
            return [SegmentAudio(**s) for s in d["segments"]], Path(d["narration"])
        segs, narration = self._stage("tts", tts_fp, ["assets/tts.json", "assets/audio/narration.wav"], tts_fn,
                                      tts_load)
        layout = editor.compute_layout(segs)

        clips = [(r.asset_id, r.sha256, r.usable_ranges, r.review_status) for r in gameplay.read_manifest()
                 if r.game == self.brief.mode]
        a_fp = fingerprint(self.brief.mode, round(layout.total_s, 3), prof.__dict__, self.seed, self.brief.music,
                           clips, "gameplay/v2")

        def assets_fn():
            bg, clip_ids = None, []
            if self.brief.mode != "og":
                bg, clip_ids = asset_generator.prepare_gameplay(self.ctx, layout.total_s, prof.width, prof.height,
                                                                prof.fps)
            music = asset_generator.prepare_music(self.ctx)
            d = {"background": str(bg) if bg else None, "clip_ids": clip_ids, "music": str(music) if music else None}
            self.job.write_json("assets/visual_assets.json", d)
            return d
        vis = self._stage("assets", a_fp, ["assets/visual_assets.json"], assets_fn,
                          lambda: self.job.read_json("assets/visual_assets.json"))

        durations = editor.scene_durations_s(storyboard, layout, prof.fps) if self.brief.mode == "og" else {}
        quality = "dev" if self.brief.dev_short else "prod"
        size = (540, 540) if self.brief.dev_short else (1080, 1080)
        palette = manim_palette(editor.video_theme(self.ctx, self.job.state.get("style", {}).get("palette")))
        m_fp = fingerprint(storyboard, durations, quality, size, palette, "manim/v2")
        has_manim = any(s.visual_type == "manim" for s in storyboard.scenes)

        def manim_fn():
            if not has_manim:
                self.job.write_json("assets/manim.json", {"clips": {}, "note": "no Manim scenes in storyboard"})
                return {}
            if not manim_runner.is_available():
                self.ctx.notes.append("Manim is not installed; Remotion diagrams used instead")
                self.job.write_json("assets/manim.json", {"clips": {}, "note": "manim unavailable"})
                return {}
            clips = asset_generator.render_manim(self.ctx, storyboard, durations, size, quality, palette)
            self.job.write_json("assets/manim.json", {"clips": clips})
            return clips
        manim = self._stage("manim", m_fp, ["assets/manim.json"], manim_fn,
                            lambda: self.job.read_json("assets/manim.json")["clips"])
        if not has_manim:
            self.job.stage_done("manim", status="skipped", fp=m_fp, artifacts=["assets/manim.json"],
                                detail="no Manim scenes")
        manifest = asset_generator.build_manifest(
            self.ctx, segs, narration, Path(vis["background"]) if vis["background"] else None, vis["clip_ids"],
            Path(vis["music"]) if vis["music"] else None, manim)
        self.job.write_json("assets/manifest.json", manifest)
        self._write_asset_csv(manifest)
        if manifest.missing:
            raise AgentFailure("assets", f"assets missing after preparation: {manifest.missing}")
        return manifest

    def _fit_rate(self, segs) -> tuple[str, str] | None:
        """A new speaking rate when the narration at the chosen speed would land outside 30-60 s (or well past
        the target): faster if too long, slower if too short. Moves at most 15 points from the chosen speed."""
        if self.brief.dev_short or self.brief.narration_audio:
            return None
        from schemas.brief import PROD_MIN_S
        speech = editor.compute_layout(segs).total_s
        limit = min(60.0, self.brief.duration_s * 1.1)
        floor = PROD_MIN_S + 1.0  # the critic fails anything under 30 s
        base = self.ctx.speed_pct
        if speech > limit:
            need = int((speech / limit - 1) * 100) + 2
            return f"{min(base + need, base + 15):+d}%", "narration was longer than the target"
        if speech < floor:
            need = int((floor / speech - 1) * 100) + 2
            return f"{max(base - need, base - 15, -30):+d}%", "narration was shorter than 30 seconds"
        return None

    def _write_asset_csv(self, manifest: AssetManifest) -> None:
        import csv

        p = self.job.path("assets/manifest.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["asset_id", "kind", "path", "exists", "sha256", "duration_s", "width", "height", "source",
                        "license", "review_status", "notes"])
            for a in manifest.assets:
                w.writerow([a.asset_id, a.kind, a.path, a.exists, a.sha256, a.duration_s, a.width, a.height, a.source,
                            a.license, a.review_status, a.notes])

    def edit_and_render(self, script: Script, storyboard: Storyboard, manifest: AssetManifest) -> tuple[RenderProps, dict]:
        style = self.job.state.get("style", {})
        e_fp = fingerprint(script, storyboard, manifest, style, editor.output_profile(self.ctx).__dict__)

        def edit_fn():
            props, caps = editor.build_timeline(self.ctx, script, storyboard, manifest,
                                                style_overrides=style.get("caption"),
                                                show_progress=style.get("show_progress", True),
                                                motion=style.get("motion"),
                                                music_volume=style.get("music_volume", 0.22))
            editor.write_caption_files(self.ctx, caps)
            self.job.write_json("render_props.json", props)
            self.job.log.log("editing", "editor", "ok", frames=props.durationInFrames, fps=props.fps,
                             captions=len(props.captions), scenes=len(props.scenes), output="render_props.json")
            return props
        props = self._stage("editing", e_fp, ["render_props.json", "captions.srt", "captions.json"], edit_fn,
                            lambda: RenderProps.model_validate(self.job.read_json("render_props.json")))
        # include media checksums: a rebuilt background can keep the same staged file name
        r_fp = fingerprint(props, manifest)
        self._stage("remotion_render", r_fp, ["render/remotion_raw.mp4"], lambda: editor.render(self.ctx, props).model_dump(),
                    lambda: None)
        f_fp = fingerprint(r_fp, self.settings.max_output_mb, "finish/v1")
        fin = self._stage("ffmpeg", f_fp, ["final.mp4", "render/finish.json"],
                          lambda: editor.finish(self.ctx, self.job.path("render/remotion_raw.mp4"), props),
                          lambda: json.loads(self.job.path("render/finish.json").read_text(encoding="utf-8")))
        return props, fin

    def qa(self, script, storyboard, facts, manifest, props, repairs: int) -> QAReport:
        self.job.stage_start("qa")
        self._notify()
        rep = critic.run(self.ctx, script, storyboard, facts, manifest, props, repairs=repairs)
        self.job.write_json("qa_report.json", rep)
        self.job.stage_done("qa", status="done" if rep.technical_pass else "failed")
        self.job.log.log("qa", "critic", "pass" if rep.technical_pass else "fail", semantic=rep.semantic_status,
                         failures=[c.name for c in rep.failures])
        self._notify()
        return rep

    # ---------- main ----------
    def run(self) -> QAReport:
        job = self.job
        job.set(status="running")
        feedback: list[str] | None = job.state.get("feedback")
        repairs = job.state.get("repairs", 0)
        try:
            while True:
                plan = self.plan()
                facts = self.research(plan)
                script = self.script(plan, facts, feedback)
                storyboard = self.storyboard(plan, script, facts)
                manifest = self.assets_and_audio(script, storyboard)
                props, _ = self.edit_and_render(script, storyboard, manifest)
                report = self.qa(script, storyboard, facts, manifest, props, repairs)
                route = self._route(report)
                failing = sorted(c.name for c in report.failures)
                if route is None or repairs >= self.settings.max_repair_attempts:
                    break
                if failing and failing == job.state.get("last_failures") and route not in ("scripting", "tts",
                                                                                              "remotion_render"):
                    job.log.log("qa", "critic", "repair_stopped", reason="the same deterministic failure repeated",
                                failures=failing)
                    break
                if route in ("scripting", "storyboarding") and not self.ctx.llm_enabled():
                    job.log.log("qa", "critic", "repair_stopped", route_to=route, failures=failing,
                                reason="local templates are deterministic; re-running them cannot fix this. "
                                       "Add sources, a user script, or an OpenRouter key.")
                    self.ctx.notes.append(f"QA asked for a {route} repair, but without an LLM the local templates "
                                          f"would produce the same result: {failing}")
                    break
                job.set(last_failures=failing)
                repairs += 1
                feedback = [f"{c.name}: {c.detail}" for c in report.checks if not c.passed and c.route_to] + \
                    (report.semantic_notes if report.semantic_status == "needs_changes" else [])
                job.log.log("qa", "critic", "repair", attempt=repairs, route_to=route, feedback=feedback)
                job.log.intervention(route, f"automatic repair #{repairs}", "; ".join(feedback)[:500],
                                     who="critic (automatic)")
                job.set(repairs=repairs, feedback=feedback)
                job.invalidate_from(route)
            status = "completed" if report.technical_pass else "failed_qa"
            if report.technical_pass and (report.semantic_status == "needs_changes" or
                                          any(not c.passed for c in report.checks)):
                status = "completed_with_warnings"
            job.set(status=status, current_stage=None, notes=self.ctx.notes,
                    outputs={"final": str(job.path("final.mp4")), "srt": str(job.path("captions.srt")),
                             "qa": str(job.path("qa_report.json"))},
                    llm_cost_usd=self.ctx.llm.job_cost if self.ctx.llm else 0.0,
                    llm_calls=self.ctx.llm.calls if self.ctx.llm else 0)
            self._notify()
            return report
        except Exception as e:
            job.set(status="failed", error=f"{type(e).__name__}: {e}", notes=self.ctx.notes)
            self._notify()
            raise

    @staticmethod
    def _route(report: QAReport) -> str | None:
        stages = [c.route_to for c in report.failures if c.route_to]
        if report.semantic_status == "needs_changes":
            stages.append("scripting")
        if not stages:
            return None
        return min(stages, key=lambda s: ROUTE_ORDER.get(s, 99))


def rerender(job_id: str, style: dict, settings: Settings | None = None, on_update=None) -> QAReport:
    """Re-render an existing job with new caption/visual style, reusing plan, research, script and storyboard."""
    p = Pipeline(job_id=job_id, settings=settings, on_update=on_update)
    p.job.log.intervention("editing", "style change and re-render", json.dumps(style)[:400])
    p.job.set(style=style)
    return p.run()


def describe_output(job: Job) -> dict:
    f = job.path("final.mp4")
    return probe(f).summary() if f.exists() else {}


