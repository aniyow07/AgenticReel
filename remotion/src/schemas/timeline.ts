// Pure timeline helpers shared by the compositions and the Vitest suite.
import type { Caption, RenderProps, Scene } from "./props";

export const secondsToFrames = (seconds: number, fps: number): number => Math.round(seconds * fps);

export interface CoverageReport {
  ok: boolean;
  gaps: Array<[number, number]>;
  overlaps: Array<[string, string]>;
}

// Scenes must tile [0, total) exactly: no gaps, no overlaps.
export const checkSceneCoverage = (scenes: Scene[], total: number): CoverageReport => {
  const sorted = [...scenes].sort((a, b) => a.startFrame - b.startFrame);
  const gaps: Array<[number, number]> = [];
  const overlaps: Array<[string, string]> = [];
  let cursor = 0;
  let prev: Scene | null = null;
  for (const s of sorted) {
    if (s.startFrame > cursor) gaps.push([cursor, s.startFrame]);
    if (prev && s.startFrame < prev.startFrame + prev.durationInFrames) overlaps.push([prev.id, s.id]);
    cursor = Math.max(cursor, s.startFrame + s.durationInFrames);
    prev = s;
  }
  if (cursor < total) gaps.push([cursor, total]);
  return { ok: gaps.length === 0 && overlaps.length === 0, gaps, overlaps };
};

export const activeCaption = (captions: Caption[], frame: number): Caption | null =>
  captions.find((c) => frame >= c.startFrame && frame < c.endFrame) ?? null;

// True when any narration caption is on screen; used for music ducking.
export const isSpeechActive = (captions: Caption[], frame: number, padFrames = 4): boolean =>
  captions.some((c) => frame >= c.startFrame - padFrames && frame < c.endFrame + padFrames);

// Splits a caption into display lines of at most maxWords words.
export const splitCaptionLines = (text: string, maxWords: number): string[] => {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  for (let i = 0; i < words.length; i += maxWords) lines.push(words.slice(i, i + maxWords).join(" "));
  return lines;
};

const normalize = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");

export const isHighlighted = (word: string, highlights: string[]): boolean => {
  const n = normalize(word);
  if (!n) return false;
  return highlights.some((h) => h.split(/\s+/).map(normalize).includes(n));
};

// Vertical anchor for captions, honouring the safe zones.
export const captionTop = (
  position: "upper" | "center" | "lower",
  height: number,
  safe: { top: number; bottom: number },
): number => {
  if (position === "upper") return safe.top;
  if (position === "lower") return height - safe.bottom - Math.round(height * 0.18);
  return Math.round(height * 0.42);
};

export const totalSceneFrames = (props: Pick<RenderProps, "scenes">): number =>
  props.scenes.reduce((m, s) => Math.max(m, s.startFrame + s.durationInFrames), 0);
