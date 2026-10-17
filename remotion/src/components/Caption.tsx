// Plain phrase-level caption used by OG mode (lower third, readable box).
import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Caption as CaptionT, Theme } from "../schemas/props";
import { scaleFor } from "../styles/theme";

export const Caption: React.FC<{ caption: CaptionT; theme: Theme; bottom: number; fontSize: number }> = ({
  caption,
  theme,
  bottom,
  fontSize,
}) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const s = scaleFor(width);
  const local = frame - caption.startFrame;
  const opacity = interpolate(local, [0, 5], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div
      style={{
        position: "absolute",
        left: s(60),
        right: s(60),
        bottom,
        display: "flex",
        justifyContent: "center",
        opacity,
      }}
    >
      <div
        style={{
          background: "rgba(5, 8, 20, 0.78)",
          color: theme.text,
          fontSize,
          fontWeight: 600,
          lineHeight: 1.25,
          padding: `${s(18)}px ${s(30)}px`,
          borderRadius: s(18),
          textAlign: "center",
          maxWidth: "100%",
        }}
      >
        {caption.text}
      </div>
    </div>
  );
};
