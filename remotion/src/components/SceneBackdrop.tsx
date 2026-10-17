// Per-scene animated backgrounds for OG videos. Each scene gets one style (picked by the storyboard or rotated by
// the Editor) and fades in over the previous scene's backdrop, so consecutive scenes never look the same.
import React, { useMemo } from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";
import { DynamicBackdrop } from "./DynamicBackdrop";

export const BACKDROP_STYLES = ["orbs", "grid", "waves", "rays", "shapes"] as const;
export type BackdropStyle = (typeof BACKDROP_STYLES)[number];

const rgba = (hex: string, a: number) => {
  const n = parseInt(hex.replace("#", "").slice(0, 6), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

const Grid: React.FC<{ theme: Theme; t: number }> = ({ theme, t }) => {
  const { width: W, height: H } = useVideoConfig();
  const hz = H * 0.42;
  const lines = [];
  for (let i = 0; i < 18; i++) {
    const z = ((i / 18 + t * 0.12) % 1) ** 2.2; // perspective: lines accelerate towards the viewer
    const y = hz + (H - hz) * z;
    lines.push(<line key={`h${i}`} x1={0} x2={W} y1={y} y2={y} stroke={rgba(theme.primary, 0.12 + 0.5 * z)} strokeWidth={1 + 3 * z} />);
  }
  for (let i = -10; i <= 10; i++) {
    lines.push(
      <line key={`v${i}`} x1={W / 2 + i * W * 0.02} y1={hz} x2={W / 2 + i * W * 0.22} y2={H} stroke={rgba(theme.primary, 0.25)} strokeWidth={2} />,
    );
  }
  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{ background: `radial-gradient(ellipse 70% 28% at 50% ${(hz / H) * 100}%, ${rgba(theme.accent, 0.45)}, transparent 70%)` }}
      />
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>{lines}</svg>
    </AbsoluteFill>
  );
};

const Waves: React.FC<{ theme: Theme; t: number }> = ({ theme, t }) => {
  const { width: W, height: H } = useVideoConfig();
  const colors = [theme.primary, theme.accent, theme.primary, theme.accent];
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      {colors.map((c, k) => {
        const base = H * (0.58 + k * 0.09);
        const amp = H * (0.035 - k * 0.005);
        const len = W * (0.9 - k * 0.12);
        let d = `M 0 ${H} L 0 ${base}`;
        for (let x = 0; x <= W; x += W / 40) {
          d += ` L ${x} ${base + amp * Math.sin((x / len) * Math.PI * 2 + t * (0.8 + k * 0.35) + k)}`;
        }
        d += ` L ${W} ${H} Z`;
        return <path key={k} d={d} fill={rgba(c, 0.14 + k * 0.05)} />;
      })}
      {colors.map((c, k) => {
        const base = H * (0.18 - k * 0.03);
        const amp = H * 0.02;
        let d = `M 0 0 L 0 ${base}`;
        for (let x = 0; x <= W; x += W / 40) d += ` L ${x} ${base + amp * Math.sin((x / W) * Math.PI * 3 - t * 0.6 + k)}`;
        d += ` L ${W} 0 Z`;
        return k < 2 ? <path key={`t${k}`} d={d} fill={rgba(c, 0.1)} /> : null;
      })}
    </svg>
  );
};

const Rays: React.FC<{ theme: Theme; t: number }> = ({ theme, t }) => {
  const stops = [];
  for (let i = 0; i < 24; i++) {
    const a = i * 15;
    stops.push(`${rgba(i % 2 ? theme.primary : theme.accent, 0.16)} ${a}deg ${a + 6}deg`, `transparent ${a + 6}deg ${a + 15}deg`);
  }
  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          background: `conic-gradient(from ${t * 7}deg at 50% 32%, ${stops.join(", ")})`,
          maskImage: "radial-gradient(circle at 50% 32%, black 0%, transparent 70%)",
        }}
      />
      <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 32%, ${rgba(theme.accent, 0.35)}, transparent 30%)` }} />
    </AbsoluteFill>
  );
};

const Shapes: React.FC<{ theme: Theme; t: number; seed: string }> = ({ theme, t, seed }) => {
  const { width: W, height: H } = useVideoConfig();
  const items = useMemo(
    () =>
      new Array(16).fill(0).map((_, i) => ({
        x: random(`${seed}-sx${i}`) * W,
        y: random(`${seed}-sy${i}`) * H,
        r: (0.03 + random(`${seed}-sr${i}`) * 0.08) * W,
        sides: [3, 4, 6][i % 3],
        spin: (random(`${seed}-ss${i}`) - 0.5) * 40,
        rise: 10 + random(`${seed}-su${i}`) * 40,
      })),
    [seed, W, H],
  );
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      {items.map((s, i) => {
        const y = ((s.y - t * s.rise) % (H + 2 * s.r) + H + 2 * s.r) % (H + 2 * s.r) - s.r;
        const pts = new Array(s.sides)
          .fill(0)
          .map((_, k) => {
            const a = (k / s.sides) * Math.PI * 2 + ((t * s.spin) / 180) * Math.PI;
            return `${s.x + s.r * Math.cos(a)},${y + s.r * Math.sin(a)}`;
          })
          .join(" ");
        return <polygon key={i} points={pts} fill="none" stroke={rgba(i % 2 ? theme.primary : theme.accent, 0.35)} strokeWidth={3} />;
      })}
    </svg>
  );
};

export const SceneBackdrop: React.FC<{
  theme: Theme;
  seed: string;
  style: BackdropStyle;
  sceneIndex: number;
  durationInFrames: number;
  fadeIn: boolean;
}> = ({ theme, seed, style, sceneIndex, durationInFrames, fadeIn }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps + sceneIndex * 7; // offset so repeated styles never start in the same pose
  const opacity = fadeIn ? interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" }) : 1;
  if (style === "orbs") {
    return (
      <AbsoluteFill style={{ opacity }}>
        <DynamicBackdrop theme={theme} seed={`${seed}-${sceneIndex}`} sceneIndex={sceneIndex}
          sceneProgress={Math.min(1, frame / Math.max(1, durationInFrames))} />
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ opacity, backgroundColor: theme.background, overflow: "hidden" }}>
      <AbsoluteFill style={{ background: `linear-gradient(160deg, ${rgba(theme.surface, 0.9)}, ${theme.background} 60%)` }} />
      {style === "grid" ? <Grid theme={theme} t={t} /> : null}
      {style === "waves" ? <Waves theme={theme} t={t} /> : null}
      {style === "rays" ? <Rays theme={theme} t={t} /> : null}
      {style === "shapes" ? <Shapes theme={theme} t={t} seed={`${seed}-${sceneIndex}`} /> : null}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.5) 100%)" }} />
    </AbsoluteFill>
  );
};
