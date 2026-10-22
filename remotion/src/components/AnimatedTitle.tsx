// Opening title card. Its layout follows the scene's backdrop, so the intro matches the look of the video
// instead of every video opening on the same card.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";
import { scaleFor } from "../styles/theme";

export type TitleLayout = "classic" | "split" | "terminal" | "frame" | "marker" | "glow";

const LAYOUT_FOR_BACKDROP: Record<string, TitleLayout> = {
  orbs: "classic", rays: "classic",
  grid: "split", contours: "split",
  matrix: "terminal", circuit: "terminal",
  hexgrid: "frame", constellation: "frame",
  shapes: "marker", stripes: "marker",
  aurora: "glow", waves: "glow",
};

export const titleLayoutFor = (backdrop?: string): TitleLayout => LAYOUT_FOR_BACKDROP[backdrop ?? ""] ?? "classic";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const AnimatedTitle: React.FC<{ title: string; subtitle?: string; theme: Theme; backdrop?: string }> = ({
  title,
  subtitle,
  theme,
  backdrop,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const s = scaleFor(width);
  const layout = titleLayoutFor(backdrop);
  const words = title.split(/\s+/).filter(Boolean);
  const pop = (i: number, delay = 4) => spring({ frame: frame - i * delay, fps, config: { damping: 14, stiffness: 120 } });
  const subStart = words.length * 4 + 10;
  const subOpacity = interpolate(frame, [subStart, subStart + 15], [0, 1], clamp);
  const sub = (extra: React.CSSProperties = {}) =>
    subtitle ? (
      <div style={{ marginTop: s(36), fontSize: s(46), color: theme.mutedText, opacity: subOpacity, fontWeight: 500, ...extra }}>
        {subtitle}
      </div>
    ) : null;

  if (layout === "split") {
    // left aligned, a tall accent bar grows beside the words as they slide in from the left
    const barH = interpolate(frame, [0, 18], [0, 100], clamp);
    return (
      <div style={{ display: "flex", alignSelf: "stretch", padding: `0 ${s(90)}px`, gap: s(44) }}>
        <div style={{ width: s(16), alignSelf: "stretch", display: "flex", alignItems: "flex-start" }}>
          <div style={{ width: "100%", height: `${barH}%`, background: theme.accent, borderRadius: s(8) }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ width: s(120) * interpolate(frame, [6, 18], [0, 1], clamp), height: s(6), background: theme.primary,
            marginBottom: s(30) }} />
          {words.map((w, i) => {
            const p = pop(i, 3);
            return (
              <span key={i} style={{ fontSize: s(112), fontWeight: 900, lineHeight: 1.02, color: i % 3 === 2 ? theme.primary : theme.text,
                opacity: p, transform: `translateX(${(1 - p) * -s(80)}px)` }}>
                {w}
              </span>
            );
          })}
          {sub()}
        </div>
      </div>
    );
  }

  if (layout === "terminal") {
    // typed out on a command line with a blinking block cursor
    const chars = Math.floor(interpolate(frame, [6, 6 + title.length * 1.3], [0, title.length], clamp));
    const done = chars >= title.length;
    const cursorOn = !done || Math.floor(frame / 12) % 2 === 0;
    const mono = "'Cascadia Mono', Consolas, 'Courier New', monospace";
    return (
      <div style={{ alignSelf: "stretch", padding: `0 ${s(80)}px`, fontFamily: mono }}>
        <div style={{ border: `${s(3)}px solid ${theme.primary}`, borderRadius: s(14), background: "rgba(0,0,0,0.82)",
          padding: s(48), opacity: interpolate(frame, [0, 8], [0, 1], clamp) }}>
          <div style={{ display: "flex", gap: s(14), marginBottom: s(36) }}>
            {[theme.accent, theme.primary, theme.mutedText].map((c, i) => (
              <div key={i} style={{ width: s(22), height: s(22), borderRadius: "50%", background: c }} />
            ))}
          </div>
          <div style={{ fontSize: s(84), fontWeight: 700, lineHeight: 1.15, color: theme.text }}>
            <span style={{ color: theme.accent }}>&gt; </span>
            {title.slice(0, chars)}
            <span style={{ display: "inline-block", width: s(44), height: s(80), marginLeft: s(8), verticalAlign: "text-bottom",
              background: cursorOn ? theme.accent : "transparent" }} />
          </div>
          {subtitle ? (
            <div style={{ marginTop: s(30), fontSize: s(40), color: theme.mutedText,
              opacity: interpolate(frame, [10 + title.length * 1.3, 24 + title.length * 1.3], [0, 1], clamp) }}>
              {"// "}{subtitle}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  if (layout === "frame") {
    // corner brackets slide in to frame a spaced-out uppercase title
    const p = spring({ frame, fps, config: { damping: 16, stiffness: 90 } });
    const off = (1 - p) * s(120);
    const arm = s(90);
    const line = `${s(8)}px solid ${theme.accent}`;
    const corner = (v: "top" | "bottom", h: "left" | "right"): React.CSSProperties => ({
      position: "absolute", width: arm, height: arm, [v]: -off, [h]: -off,
      [`border${v === "top" ? "Top" : "Bottom"}`]: line, [`border${h === "left" ? "Left" : "Right"}`]: line,
    });
    const spacing = interpolate(frame, [0, 30], [s(30), s(6)], clamp);
    return (
      <div style={{ position: "relative", margin: `0 ${s(90)}px`, padding: `${s(70)}px ${s(56)}px`, textAlign: "center" }}>
        <div style={corner("top", "left")} />
        <div style={corner("top", "right")} />
        <div style={corner("bottom", "left")} />
        <div style={corner("bottom", "right")} />
        <div style={{ fontSize: s(92), fontWeight: 800, lineHeight: 1.12, textTransform: "uppercase", letterSpacing: spacing,
          color: theme.text, opacity: interpolate(frame, [4, 20], [0, 1], clamp) }}>
          {title}
        </div>
        {sub({ letterSpacing: s(4) })}
      </div>
    );
  }

  if (layout === "marker") {
    // a highlighter swipe behind each word, slightly tilted, words bounce in
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: s(80),
        transform: "rotate(-3deg)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `${s(10)}px ${s(20)}px` }}>
          {words.map((w, i) => {
            const p = pop(i, 5);
            const swipe = interpolate(frame, [i * 5 + 6, i * 5 + 16], [0, 100], clamp);
            return (
              <span key={i} style={{ fontSize: s(110), fontWeight: 900, lineHeight: 1.1, color: theme.text, padding: `0 ${s(10)}px`,
                display: "inline-block", opacity: p, transform: `scale(${0.6 + 0.4 * p})`,
                background: `linear-gradient(${i % 2 ? theme.primary : theme.accent}, ${i % 2 ? theme.primary : theme.accent}) no-repeat`,
                backgroundSize: `${swipe}% 42%`, backgroundPosition: "0 88%" }}>
                {w}
              </span>
            );
          })}
        </div>
        {sub({ fontWeight: 700 })}
      </div>
    );
  }

  if (layout === "glow") {
    // thin rules open outwards above and below while the title fades up out of a soft blur
    const rule = interpolate(frame, [0, 24], [0, 100], clamp);
    const blur = interpolate(frame, [0, 26], [s(24), 0], clamp);
    const r = (
      <div style={{ width: `${rule}%`, maxWidth: s(700), height: s(3),
        background: `linear-gradient(90deg, transparent, ${theme.accent}, transparent)` }} />
    );
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: s(80), gap: s(50) }}>
        {r}
        <div style={{ fontSize: s(100), fontWeight: 300, lineHeight: 1.15, color: theme.text, filter: `blur(${blur}px)`,
          opacity: interpolate(frame, [0, 20], [0, 1], clamp), textShadow: `0 0 ${s(40)}px ${theme.accent}` }}>
          {title}
        </div>
        {r}
        {subtitle ? <div style={{ fontSize: s(44), color: theme.mutedText, opacity: subOpacity, fontStyle: "italic" }}>{subtitle}</div> : null}
      </div>
    );
  }

  const barWidth = interpolate(frame, [0, 20], [0, 100], { extrapolateRight: "clamp" });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: s(80) }}>
      <div style={{ width: `${barWidth}%`, maxWidth: s(320), height: s(10), borderRadius: s(5), background: theme.accent, marginBottom: s(40) }} />
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `0 ${s(22)}px` }}>
        {words.map((w, i) => {
          const p = pop(i);
          return (
            <span key={i} style={{ fontSize: s(104), fontWeight: 800, lineHeight: 1.1, color: theme.text, opacity: p,
              transform: `translateY(${(1 - p) * s(60)}px)`, display: "inline-block" }}>
              {w}
            </span>
          );
        })}
      </div>
      {sub()}
    </div>
  );
};
