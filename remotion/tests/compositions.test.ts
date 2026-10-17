import { describe, expect, it } from "vitest";
import { calculateMetadata } from "../src/Root";
import { COMPOSITIONS } from "../src/compositions/registry";
import { makeDefaultProps } from "../src/defaultProps";
import { PublicPathSchema, RenderPropsSchema } from "../src/schemas/props";
import {
  activeCaption,
  captionTop,
  checkSceneCoverage,
  isHighlighted,
  isSpeechActive,
  secondsToFrames,
  splitCaptionLines,
} from "../src/schemas/timeline";

describe("composition registration", () => {
  it("registers exactly the three modes with stable ids", () => {
    expect(COMPOSITIONS.map((c) => [c.id, c.mode])).toEqual([
      ["OGVideo", "og"],
      ["MinecraftBrainrot", "minecraft"],
      ["SubwayBrainrot", "subway"],
    ]);
    for (const c of COMPOSITIONS) expect(typeof c.component).toBe("function");
  });

  it("derives size, fps and duration from validated props", () => {
    const p = { ...makeDefaultProps("og"), durationInFrames: 321, width: 540, height: 960, fps: 30 };
    const meta = calculateMetadata({ props: p, compositionId: "OGVideo" });
    expect(meta).toMatchObject({ durationInFrames: 321, width: 540, height: 960, fps: 30 });
  });

  it("refuses props whose mode does not match the composition", () => {
    expect(() => calculateMetadata({ props: makeDefaultProps("og"), compositionId: "SubwayBrainrot" })).toThrow(
      /expects mode "subway"/,
    );
  });
});

describe("prop validation", () => {
  it("accepts the default props of every mode", () => {
    for (const m of ["og", "minecraft", "subway"] as const) {
      expect(RenderPropsSchema.safeParse(makeDefaultProps(m)).success).toBe(true);
    }
  });

  it("rejects brainrot props without a gameplay background (missing asset)", () => {
    const p = { ...makeDefaultProps("minecraft"), background: [] };
    const r = RenderPropsSchema.safeParse(p);
    expect(r.success).toBe(false);
    expect(JSON.stringify(r.error?.issues)).toMatch(/gameplay background/);
  });

  it("rejects captions and scenes outside the timeline", () => {
    const p = makeDefaultProps("og");
    p.captions = [{ id: "c", text: "x", startFrame: 100, endFrame: 400, highlights: [], motion: 1 }];
    expect(RenderPropsSchema.safeParse(p).success).toBe(false);
    const q = makeDefaultProps("og");
    q.scenes[0].durationInFrames = 999;
    expect(RenderPropsSchema.safeParse(q).success).toBe(false);
  });

  it("rejects unknown visual types and malformed params", () => {
    const p = makeDefaultProps("og") as unknown as { scenes: Array<Record<string, unknown>> };
    p.scenes[0] = { ...p.scenes[0], visualType: "exec_code", params: { code: "x" } };
    expect(RenderPropsSchema.safeParse(p).success).toBe(false);
    const q = makeDefaultProps("og") as unknown as { scenes: Array<Record<string, unknown>> };
    q.scenes[0] = { ...q.scenes[0], visualType: "process", params: { steps: ["only one"] } };
    expect(RenderPropsSchema.safeParse(q).success).toBe(false);
  });

  it("only allows media paths relative to the public dir", () => {
    for (const ok of ["gameplay/background.mp4", "manim/S02_abc.mp4", "audio/narration.wav"]) {
      expect(PublicPathSchema.safeParse(ok).success).toBe(true);
    }
    for (const bad of ["C:\\clips\\a.mp4", "C:/clips/a.mp4", "/abs/a.mp4", "../a.mp4", "a/../../b.mp4", "https://x/a.mp4"]) {
      expect(PublicPathSchema.safeParse(bad).success).toBe(false);
    }
  });
});

describe("timeline maths", () => {
  it("converts seconds to frames with the composition fps", () => {
    expect(secondsToFrames(1.5, 30)).toBe(45);
    expect(secondsToFrames(1.5, 24)).toBe(36);
    expect(secondsToFrames(0.0166, 30)).toBe(0);
  });

  it("detects gaps and overlaps in scene coverage", () => {
    const base = makeDefaultProps("og").scenes[0];
    const ok = checkSceneCoverage(
      [
        { ...base, id: "a", startFrame: 0, durationInFrames: 50 },
        { ...base, id: "b", startFrame: 50, durationInFrames: 100 },
      ],
      150,
    );
    expect(ok.ok).toBe(true);
    const bad = checkSceneCoverage(
      [
        { ...base, id: "a", startFrame: 0, durationInFrames: 60 },
        { ...base, id: "b", startFrame: 50, durationInFrames: 80 },
      ],
      150,
    );
    expect(bad.overlaps).toEqual([["a", "b"]]);
    expect(bad.gaps).toEqual([[130, 150]]);
  });

  it("finds the active caption and ducks music around speech", () => {
    const caps = [
      { id: "1", text: "a b", startFrame: 10, endFrame: 20, highlights: [], motion: 1 },
      { id: "2", text: "c d", startFrame: 40, endFrame: 50, highlights: [], motion: 1 },
    ];
    expect(activeCaption(caps, 15)?.id).toBe("1");
    expect(activeCaption(caps, 20)).toBeNull();
    expect(isSpeechActive(caps, 8)).toBe(true);
    expect(isSpeechActive(caps, 30)).toBe(false);
  });
});

describe("caption layout", () => {
  it("splits captions into short lines", () => {
    expect(splitCaptionLines("one two three four five", 2)).toEqual(["one two", "three four", "five"]);
  });

  it("matches highlights ignoring case and punctuation", () => {
    expect(isHighlighted("Electrolysis,", ["electrolysis"])).toBe(true);
    expect(isHighlighted("water", ["clean water"])).toBe(true);
    expect(isHighlighted("the", ["electrolysis"])).toBe(false);
  });

  it("keeps captions inside the vertical safe zones", () => {
    const safe = { top: 250, bottom: 350 };
    expect(captionTop("upper", 1920, safe)).toBe(250);
    const lower = captionTop("lower", 1920, safe);
    expect(lower + Math.round(1920 * 0.18)).toBeLessThanOrEqual(1920 - 350);
    const center = captionTop("center", 1920, safe);
    expect(center).toBeGreaterThan(250);
    expect(center).toBeLessThan(1920 - 350);
  });
});
