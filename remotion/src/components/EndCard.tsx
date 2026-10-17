import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";
import { scaleFor } from "../styles/theme";

export const EndCard: React.FC<{ text: string; cta?: string; theme: Theme }> = ({ text, cta, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const s = scaleFor(width);
  const p = spring({ frame, fps, config: { damping: 15 } });
  const p2 = spring({ frame: frame - 10, fps, config: { damping: 12 } });
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: s(80) }}>
      <div style={{ fontSize: s(80), fontWeight: 800, color: theme.text, opacity: p, transform: `scale(${0.85 + 0.15 * p})` }}>
        {text}
      </div>
      {cta ? (
        <div
          style={{
            marginTop: s(50),
            padding: `${s(24)}px ${s(48)}px`,
            borderRadius: s(60),
            background: theme.accent,
            color: "#111",
            fontSize: s(48),
            fontWeight: 700,
            opacity: p2,
            transform: `translateY(${(1 - p2) * s(40)}px)`,
          }}
        >
          {cta}
        </div>
      ) : null}
    </div>
  );
};
