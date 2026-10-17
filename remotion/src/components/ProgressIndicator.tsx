import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

export const ProgressIndicator: React.FC<{ color: string; top: number }> = ({ color, top }) => {
  const frame = useCurrentFrame();
  const { durationInFrames, width } = useVideoConfig();
  const pct = Math.min(100, ((frame + 1) / durationInFrames) * 100);
  const h = Math.max(6, Math.round((12 * width) / 1080));
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: "8%",
        width: "84%",
        height: h,
        borderRadius: h,
        background: "rgba(255,255,255,0.25)",
        overflow: "hidden",
      }}
    >
      <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: h }} />
    </div>
  );
};
