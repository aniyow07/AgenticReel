// Animated OG background: drifting gradient blobs, a slowly rotating ring system, a parallax dot
// grid and floating particles. Every element is driven by the frame and a per-video seed, so two
// reels never share the same motion, and the accent shifts with each scene.
import React, { useMemo } from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";

const hexToRgb = (hex: string): [number, number, number] => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const rgba = (hex: string, a: number) => {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${a})`;
};

export const DynamicBackdrop: React.FC<{ theme: Theme; seed: string; sceneIndex: number; sceneProgress: number }> = ({
  theme,
  seed,
  sceneIndex,
  sceneProgress,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const t = frame / fps;
  const palette = [theme.primary, theme.accent, theme.text];

  const blobs = useMemo(
    () =>
      new Array(4).fill(0).map((_, i) => ({
        x: random(`${seed}-bx${i}`) * 100,
        y: random(`${seed}-by${i}`) * 100,
        r: 35 + random(`${seed}-br${i}`) * 30,
        sx: 0.05 + random(`${seed}-sx${i}`) * 0.12,
        sy: 0.04 + random(`${seed}-sy${i}`) * 0.1,
        ph: random(`${seed}-ph${i}`) * Math.PI * 2,
      })),
    [seed],
  );
  const particles = useMemo(
    () =>
      new Array(36).fill(0).map((_, i) => ({
        x: random(`${seed}-px${i}`),
        speed: 0.015 + random(`${seed}-ps${i}`) * 0.05,
        size: 2 + random(`${seed}-pz${i}`) * 6,
        off: random(`${seed}-po${i}`),
        drift: (random(`${seed}-pd${i}`) - 0.5) * 0.08,
        color: palette[i % 2],
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [seed, theme.primary, theme.accent],
  );

  // Each scene rotates the accent emphasis so consecutive scenes feel different.
  const sceneColor = palette[sceneIndex % 2];
  const ringRot = t * 8 + sceneIndex * 40;
  const ringScale = 1 + 0.05 * Math.sin(t * 0.9);
  const gridShift = (t * 12) % 60;
  const sweep = interpolate(sceneProgress, [0, 1], [-30, 130]);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.background, overflow: "hidden" }}>
      {/* drifting colour blobs */}
      <AbsoluteFill
        style={{
          background: blobs
            .map((b, i) => {
              const x = b.x + 22 * Math.sin(t * b.sx * 6 + b.ph);
              const y = b.y + 18 * Math.cos(t * b.sy * 6 + b.ph);
              const c = i === 0 ? sceneColor : palette[i % 2];
              return `radial-gradient(circle at ${x}% ${y}%, ${rgba(c, 0.32)} 0%, transparent ${b.r}%)`;
            })
            .join(", "),
          filter: "blur(10px)",
        }}
      />
      {/* parallax dot grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(${rgba(theme.text, 0.09)} 1.5px, transparent 1.6px)`,
          backgroundSize: "60px 60px",
          backgroundPosition: `${gridShift}px ${gridShift * 0.6}px`,
          maskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)",
        }}
      />
      {/* rotating ring system */}
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        <g
          transform={`translate(${width * (0.5 + 0.18 * Math.sin(t * 0.3))} ${height * (0.45 + 0.1 * Math.cos(t * 0.25))}) rotate(${ringRot}) scale(${ringScale})`}
        >
          {[0.28, 0.4, 0.52].map((r, i) => (
            <circle
              key={i}
              r={Math.min(width, height) * r}
              fill="none"
              stroke={rgba(i === 1 ? sceneColor : theme.text, i === 1 ? 0.22 : 0.07)}
              strokeWidth={i === 1 ? 3 : 2}
              strokeDasharray={i === 1 ? "28 18" : "6 14"}
            />
          ))}
        </g>
      </svg>
      {/* floating particles */}
      {particles.map((p, i) => {
        const y = (1 - ((p.off + t * p.speed) % 1)) * (height + 40) - 20;
        const x = (p.x + Math.sin(t * 0.7 + i) * 0.02 + p.drift * t * 0.1) * width;
        const o = 0.25 + 0.35 * Math.sin(t * 1.3 + i);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: ((x % width) + width) % width,
              top: y,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: p.color,
              opacity: Math.max(0.08, o),
              boxShadow: `0 0 ${p.size * 3}px ${rgba(p.color, 0.6)}`,
            }}
          />
        );
      })}
      {/* light sweep across each scene */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(115deg, transparent ${sweep - 12}%, ${rgba(theme.text, 0.05)} ${sweep}%, transparent ${sweep + 12}%)`,
        }}
      />
      {/* vignette */}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.45) 100%)" }} />
    </AbsoluteFill>
  );
};
