import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";
import { scaleFor } from "../styles/theme";

export const AnimatedTitle: React.FC<{ title: string; subtitle?: string; theme: Theme }> = ({
  title,
  subtitle,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const s = scaleFor(width);
  const words = title.split(/\s+/).filter(Boolean);
  const barWidth = interpolate(frame, [0, 20], [0, 100], { extrapolateRight: "clamp" });
  const subOpacity = interpolate(frame, [words.length * 4 + 10, words.length * 4 + 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: s(80) }}>
      <div
        style={{
          width: `${barWidth}%`,
          maxWidth: s(320),
          height: s(10),
          borderRadius: s(5),
          background: theme.accent,
          marginBottom: s(40),
        }}
      />
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `0 ${s(22)}px` }}>
        {words.map((w, i) => {
          const p = spring({ frame: frame - i * 4, fps, config: { damping: 14, stiffness: 120 } });
          return (
            <span
              key={i}
              style={{
                fontSize: s(104),
                fontWeight: 800,
                lineHeight: 1.1,
                color: theme.text,
                opacity: p,
                transform: `translateY(${(1 - p) * s(60)}px)`,
                display: "inline-block",
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
      {subtitle ? (
        <div style={{ marginTop: s(36), fontSize: s(48), color: theme.mutedText, opacity: subOpacity, fontWeight: 500 }}>
          {subtitle}
        </div>
      ) : null}
    </div>
  );
};
