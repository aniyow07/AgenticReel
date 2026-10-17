// Trusted renderers for every OG visual type. Each takes validated params only.
import React from "react";
import { Freeze, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";
import { scaleFor } from "../styles/theme";

type P<T> = { params: T; theme: Theme };

const useS = () => scaleFor(useVideoConfig().width);

const Heading: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => {
  const s = useS();
  const frame = useCurrentFrame();
  if (!text) return null;
  const o = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ fontSize: s(64), fontWeight: 800, color: theme.text, marginBottom: s(50), opacity: o, textAlign: "center" }}>
      {text}
    </div>
  );
};

const Column: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const s = useS();
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch", width: "100%", padding: `0 ${s(80)}px` }}>
      {children}
    </div>
  );
};

export const TextReveal: React.FC<P<{ text: string }>> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const s = useS();
  const words = params.text.split(/\s+/);
  return (
    <div style={{ padding: s(90), fontSize: s(70), fontWeight: 700, lineHeight: 1.3, textAlign: "center", color: theme.text }}>
      {words.map((w, i) => {
        const o = interpolate(frame - i * 2, [0, 8], [0.15, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <span key={i} style={{ opacity: o }}>
            {w}{" "}
          </span>
        );
      })}
    </div>
  );
};

export const KeyPoints: React.FC<P<{ heading: string; points: string[] }>> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useS();
  return (
    <Column>
      <Heading text={params.heading} theme={theme} />
      {params.points.map((pt, i) => {
        const p = spring({ frame: frame - 8 - i * 10, fps, config: { damping: 14 } });
        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: s(28),
              background: theme.surface,
              borderLeft: `${s(10)}px solid ${i % 2 ? theme.accent : theme.primary}`,
              borderRadius: s(20),
              padding: `${s(28)}px ${s(34)}px`,
              marginBottom: s(26),
              opacity: p,
              transform: `translateX(${(1 - p) * s(-80)}px)`,
            }}
          >
            <div style={{ fontSize: s(48), fontWeight: 800, color: i % 2 ? theme.accent : theme.primary }}>{i + 1}</div>
            <div style={{ fontSize: s(46), color: theme.text, fontWeight: 600, lineHeight: 1.25 }}>{pt}</div>
          </div>
        );
      })}
    </Column>
  );
};

export const StatCounter: React.FC<
  P<{ value: number; prefix: string; suffix: string; label: string; sourceNote: string }>
> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const s = useS();
  const progress = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });
  const eased = 1 - Math.pow(1 - progress, 3);
  const decimals = Number.isInteger(params.value) ? 0 : 1;
  const shown = (params.value * eased).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: s(80) }}>
      <div style={{ fontSize: s(190), fontWeight: 900, color: theme.accent, lineHeight: 1 }}>
        {params.prefix}
        {shown}
        {params.suffix}
      </div>
      <div style={{ fontSize: s(54), color: theme.text, marginTop: s(30), fontWeight: 600 }}>{params.label}</div>
      {params.sourceNote ? (
        <div style={{ fontSize: s(30), color: theme.mutedText, marginTop: s(30) }}>Source: {params.sourceNote}</div>
      ) : null}
    </div>
  );
};

export const TimelineScene: React.FC<P<{ heading: string; events: { label: string; detail: string }[] }>> = ({
  params,
  theme,
}) => {
  const frame = useCurrentFrame();
  const s = useS();
  const n = params.events.length;
  const line = interpolate(frame, [0, 12 * n], [0, 100], { extrapolateRight: "clamp" });
  return (
    <Column>
      <Heading text={params.heading} theme={theme} />
      <div style={{ position: "relative", paddingLeft: s(70) }}>
        <div
          style={{
            position: "absolute",
            left: s(24),
            top: 0,
            width: s(8),
            height: `${line}%`,
            background: theme.primary,
            borderRadius: s(4),
          }}
        />
        {params.events.map((ev, i) => {
          const o = interpolate(frame - i * 12, [0, 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={i} style={{ position: "relative", marginBottom: s(50), opacity: o }}>
              <div
                style={{
                  position: "absolute",
                  left: s(-60),
                  top: s(10),
                  width: s(34),
                  height: s(34),
                  borderRadius: "50%",
                  background: theme.accent,
                }}
              />
              <div style={{ fontSize: s(50), fontWeight: 800, color: theme.text }}>{ev.label}</div>
              {ev.detail ? <div style={{ fontSize: s(38), color: theme.mutedText, marginTop: s(8) }}>{ev.detail}</div> : null}
            </div>
          );
        })}
      </div>
    </Column>
  );
};

export const ProcessDiagram: React.FC<P<{ heading: string; steps: string[] }>> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useS();
  return (
    <Column>
      <Heading text={params.heading} theme={theme} />
      {params.steps.map((st, i) => {
        const p = spring({ frame: frame - i * 12, fps, config: { damping: 14 } });
        return (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", opacity: p }}>
            <div
              style={{
                width: "100%",
                textAlign: "center",
                background: theme.surface,
                border: `${s(4)}px solid ${theme.primary}`,
                borderRadius: s(24),
                padding: `${s(26)}px ${s(30)}px`,
                fontSize: s(46),
                fontWeight: 700,
                color: theme.text,
                transform: `scale(${0.85 + 0.15 * p})`,
              }}
            >
              {st}
            </div>
            {i < params.steps.length - 1 ? (
              <div style={{ fontSize: s(56), color: theme.accent, lineHeight: 1.2 }}>▼</div>
            ) : null}
          </div>
        );
      })}
    </Column>
  );
};

export const Comparison: React.FC<
  P<{ heading: string; leftTitle: string; rightTitle: string; leftPoints: string[]; rightPoints: string[] }>
> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const s = useS();
  const side = (title: string, pts: string[], color: string, delay: number) => {
    const o = interpolate(frame - delay, [0, 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    return (
      <div style={{ flex: 1, background: theme.surface, borderRadius: s(24), padding: s(30), opacity: o, borderTop: `${s(10)}px solid ${color}` }}>
        <div style={{ fontSize: s(46), fontWeight: 800, color, marginBottom: s(20) }}>{title}</div>
        {pts.map((p, i) => (
          <div key={i} style={{ fontSize: s(36), color: theme.text, marginBottom: s(14), lineHeight: 1.25 }}>
            • {p}
          </div>
        ))}
      </div>
    );
  };
  return (
    <Column>
      <Heading text={params.heading} theme={theme} />
      <div style={{ display: "flex", gap: s(26) }}>
        {side(params.leftTitle, params.leftPoints, theme.primary, 0)}
        {side(params.rightTitle, params.rightPoints, theme.accent, 10)}
      </div>
    </Column>
  );
};

export const BarChart: React.FC<
  P<{ heading: string; labels: string[]; values: number[]; unit: string; sourceNote: string }>
> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const s = useS();
  const max = Math.max(...params.values.map((v) => Math.abs(v)), 1e-9);
  return (
    <Column>
      <Heading text={params.heading} theme={theme} />
      {params.labels.map((label, i) => {
        const v = params.values[i] ?? 0;
        const grow = interpolate(frame - i * 6, [0, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <div key={i} style={{ marginBottom: s(26) }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: s(36), color: theme.text, marginBottom: s(8) }}>
              <span>{label}</span>
              <span style={{ fontWeight: 800 }}>
                {v.toLocaleString("en-US")}
                {params.unit}
              </span>
            </div>
            <div style={{ height: s(44), background: "rgba(255,255,255,0.08)", borderRadius: s(12) }}>
              <div
                style={{
                  height: "100%",
                  width: `${(Math.abs(v) / max) * 100 * grow}%`,
                  background: i % 2 ? theme.accent : theme.primary,
                  borderRadius: s(12),
                }}
              />
            </div>
          </div>
        );
      })}
      {params.sourceNote ? (
        <div style={{ fontSize: s(28), color: theme.mutedText, marginTop: s(10) }}>Source: {params.sourceNote}</div>
      ) : null}
    </Column>
  );
};

export const ImageScene: React.FC<P<{ src: string; caption: string }>> = ({ params, theme }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const s = useS();
  const zoom = interpolate(frame, [0, durationInFrames], [1, 1.08]);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "100%", padding: s(60) }}>
      <div style={{ width: "100%", borderRadius: s(24), overflow: "hidden" }}>
        <Img src={staticFile(params.src)} style={{ width: "100%", transform: `scale(${zoom})`, display: "block" }} />
      </div>
      {params.caption ? <div style={{ fontSize: s(40), color: theme.text, marginTop: s(24) }}>{params.caption}</div> : null}
    </div>
  );
};

export const ManimClip: React.FC<P<{ src: string; heading: string; clipDurationInFrames?: number }>> = ({
  params,
  theme,
}) => {
  const s = useS();
  const frame = useCurrentFrame();
  // WebM clips carry an alpha channel: the diagram floats directly on the animated backdrop (no dark box).
  const alpha = params.src.toLowerCase().endsWith(".webm");
  const video = (
    <OffthreadVideo src={staticFile(params.src)} muted transparent={alpha} style={{ width: "100%", display: "block" }} />
  );
  const last = params.clipDurationInFrames ? params.clipDurationInFrames - 1 : null;
  const box = alpha
    ? { width: "100%" }
    : { width: "100%", borderRadius: s(24), overflow: "hidden", border: `${s(4)}px solid ${theme.surface}` };
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "100%", padding: `0 ${s(40)}px` }}>
      <Heading text={params.heading} theme={theme} />
      <div style={box}>
        {last !== null && frame >= last ? <Freeze frame={last}>{video}</Freeze> : video}
      </div>
    </div>
  );
};
