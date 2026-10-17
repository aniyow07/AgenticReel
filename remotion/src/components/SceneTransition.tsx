// Wraps a scene and applies a short entry/exit transition inside its own Sequence.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export const SceneTransition: React.FC<{
  type: "fade" | "slide" | "zoom" | "none";
  durationInFrames: number;
  children: React.ReactNode;
}> = ({ type, durationInFrames, children }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const t = Math.min(10, Math.floor(durationInFrames / 4));
  // slow continuous drift so content keeps moving while the narration plays
  const drift = 1 + 0.03 * (frame / Math.max(1, durationInFrames));
  if (type === "none" || t < 1) return <AbsoluteFill style={{ transform: `scale(${drift})` }}>{children}</AbsoluteFill>;
  const enter = interpolate(frame, [0, t], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const exit = interpolate(frame, [durationInFrames - t, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = Math.min(enter, exit);
  let transform = `scale(${drift})`;
  if (type === "slide") transform = `translateX(${(1 - enter) * width * 0.15 - (1 - exit) * width * 0.1}px) scale(${drift})`;
  if (type === "zoom") transform = `scale(${(0.9 + 0.1 * enter) * drift * (1 + 0.06 * (1 - exit))})`;
  if (type === "fade") transform = `translateY(${(1 - enter) * 40}px) scale(${drift})`;
  return <AbsoluteFill style={{ opacity, transform }}>{children}</AbsoluteFill>;
};
