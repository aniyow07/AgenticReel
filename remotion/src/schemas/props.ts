// Zod schemas for every prop the AgentReel compositions accept.
// The Python side (schemas/render_props.py) mirrors these with Pydantic;
// both validate, so a malformed render_props.json fails before any frame renders.
import { z } from "zod";

export const ModeSchema = z.enum(["og", "minecraft", "subway"]);

// A path relative to the public directory, resolved with staticFile().
// Absolute paths, URLs, drive letters and traversal are rejected.
export const PublicPathSchema = z
  .string()
  .min(1)
  .refine((p) => !/^[a-zA-Z]:/.test(p) && !p.startsWith("/") && !p.startsWith("\\"), {
    message: "media path must be relative to the public directory",
  })
  .refine((p) => !p.split(/[\\/]/).includes(".."), { message: "path traversal is not allowed" })
  .refine((p) => !/^[a-z]+:\/\//i.test(p), { message: "remote URLs are not allowed" });

export const CaptionSchema = z.object({
  id: z.string(),
  text: z.string().min(1),
  startFrame: z.number().int().nonnegative(),
  endFrame: z.number().int().positive(),
  highlights: z.array(z.string()).default([]),
  // camera reaction when this caption appears: 0 calm, 1 normal, 2 strong, 3 hit
  motion: z.number().int().min(0).max(3).default(1),
});

export const CaptionStyleSchema = z.object({
  fontSize: z.number().min(24).max(160).default(72),
  color: z.string().default("#FFFFFF"),
  highlightColor: z.string().default("#FFE135"),
  outlineColor: z.string().default("#000000"),
  outlineWidth: z.number().min(0).max(20).default(8),
  position: z.enum(["upper", "center", "lower"]).default("center"),
  animation: z.enum(["pop", "fade", "slide", "none"]).default("pop"),
  emphasis: z.number().min(0).max(1).default(0.6),
  uppercase: z.boolean().default(true),
  maxWordsPerLine: z.number().int().min(1).max(10).default(4),
});

export const AudioTrackSchema = z.object({
  src: PublicPathSchema,
  volume: z.number().min(0).max(2).default(1),
});

export const MusicSchema = z.object({
  src: PublicPathSchema,
  volume: z.number().min(0).max(1).default(0.25),
  duckedVolume: z.number().min(0).max(1).default(0.08),
});

// ---- OG scene parameter shapes (trusted renderers only, never code) ----
const TitleParams = z.object({ title: z.string(), subtitle: z.string().default("") });
const TextRevealParams = z.object({ text: z.string() });
const KeyPointsParams = z.object({ heading: z.string().default(""), points: z.array(z.string()).min(1).max(6) });
const StatParams = z.object({
  value: z.number(),
  prefix: z.string().default(""),
  suffix: z.string().default(""),
  label: z.string(),
  sourceNote: z.string().default(""),
});
const TimelineParams = z.object({
  heading: z.string().default(""),
  events: z.array(z.object({ label: z.string(), detail: z.string().default("") })).min(2).max(6),
});
const ProcessParams = z.object({ heading: z.string().default(""), steps: z.array(z.string()).min(2).max(6) });
const ComparisonParams = z.object({
  heading: z.string().default(""),
  leftTitle: z.string(),
  rightTitle: z.string(),
  leftPoints: z.array(z.string()).min(1).max(5),
  rightPoints: z.array(z.string()).min(1).max(5),
});
const ChartParams = z.object({
  heading: z.string().default(""),
  labels: z.array(z.string()).min(1).max(8),
  values: z.array(z.number()).min(1).max(8),
  unit: z.string().default(""),
  sourceNote: z.string().default(""),
});
const ImageParams = z.object({ src: PublicPathSchema, caption: z.string().default("") });
const ManimParams = z.object({
  src: PublicPathSchema,
  heading: z.string().default(""),
  // Length of the rendered clip; the last frame is held if the scene runs longer.
  clipDurationInFrames: z.number().int().positive().optional(),
});
const EndCardParams = z.object({ text: z.string(), cta: z.string().default("") });

const base = {
  id: z.string(),
  startFrame: z.number().int().nonnegative(),
  durationInFrames: z.number().int().positive(),
  transition: z.enum(["fade", "slide", "zoom", "none"]).default("fade"),
  // animated background style for this scene (OG)
  backdrop: z.enum(["orbs", "grid", "waves", "rays", "shapes", "aurora", "constellation", "hexgrid", "circuit",
    "contours", "stripes", "matrix"]).default("orbs"),
};

export const SceneSchema = z.discriminatedUnion("visualType", [
  z.object({ ...base, visualType: z.literal("title"), params: TitleParams }),
  z.object({ ...base, visualType: z.literal("text_reveal"), params: TextRevealParams }),
  z.object({ ...base, visualType: z.literal("key_points"), params: KeyPointsParams }),
  z.object({ ...base, visualType: z.literal("stat"), params: StatParams }),
  z.object({ ...base, visualType: z.literal("timeline"), params: TimelineParams }),
  z.object({ ...base, visualType: z.literal("process"), params: ProcessParams }),
  z.object({ ...base, visualType: z.literal("comparison"), params: ComparisonParams }),
  z.object({ ...base, visualType: z.literal("chart"), params: ChartParams }),
  z.object({ ...base, visualType: z.literal("image"), params: ImageParams }),
  z.object({ ...base, visualType: z.literal("manim"), params: ManimParams }),
  z.object({ ...base, visualType: z.literal("end_card"), params: EndCardParams }),
]);

export const BackgroundSegmentSchema = z.object({
  src: PublicPathSchema,
  startFrame: z.number().int().nonnegative(),
  durationInFrames: z.number().int().positive(),
  trimBeforeFrames: z.number().int().nonnegative().default(0),
});

export const ThemeSchema = z.object({
  name: z.string().default("default"),
  background: z.string().default("#0B1020"),
  surface: z.string().default("#151C33"),
  primary: z.string().default("#7C9CFF"),
  accent: z.string().default("#FFB547"),
  text: z.string().default("#F5F7FF"),
  mutedText: z.string().default("#A9B2D0"),
  fontFamily: z.string().default("'Segoe UI', 'Helvetica Neue', Arial, sans-serif"),
});

export const RenderPropsSchema = z
  .object({
    mode: ModeSchema,
    fps: z.number().int().min(10).max(60),
    width: z.number().int().min(160).max(3840),
    height: z.number().int().min(160).max(3840),
    durationInFrames: z.number().int().positive(),
    title: z.string().default(""),
    narration: AudioTrackSchema.nullable().default(null),
    music: MusicSchema.nullable().default(null),
    captions: z.array(CaptionSchema).default([]),
    captionStyle: CaptionStyleSchema.default({}),
    showCaptions: z.boolean().default(true),
    scenes: z.array(SceneSchema).default([]),
    background: z.array(BackgroundSegmentSchema).default([]),
    showProgress: z.boolean().default(true),
    zoomEffects: z.boolean().default(true),
    motionIntensity: z.number().min(0).max(2).default(1),
    theme: ThemeSchema.default({}),
    safeZone: z.object({ top: z.number().int().nonnegative(), bottom: z.number().int().nonnegative() }).default({
      top: 250,
      bottom: 350,
    }),
  })
  .superRefine((p, ctx) => {
    for (const c of p.captions) {
      if (c.endFrame <= c.startFrame) {
        ctx.addIssue({ code: "custom", message: `caption ${c.id} ends before it starts` });
      }
      if (c.endFrame > p.durationInFrames) {
        ctx.addIssue({ code: "custom", message: `caption ${c.id} extends past the video end` });
      }
    }
    for (const s of p.scenes) {
      if (s.startFrame + s.durationInFrames > p.durationInFrames) {
        ctx.addIssue({ code: "custom", message: `scene ${s.id} extends past the video end` });
      }
    }
    if (p.mode !== "og" && p.background.length === 0) {
      ctx.addIssue({ code: "custom", message: `${p.mode} mode requires at least one gameplay background segment` });
    }
    if (p.mode === "og" && p.scenes.length === 0) {
      ctx.addIssue({ code: "custom", message: "og mode requires at least one scene" });
    }
  });

export type RenderProps = z.infer<typeof RenderPropsSchema>;
export type Scene = z.infer<typeof SceneSchema>;
export type Caption = z.infer<typeof CaptionSchema>;
export type CaptionStyle = z.infer<typeof CaptionStyleSchema>;
export type Theme = z.infer<typeof ThemeSchema>;

