// Big outlined brainrot caption with keyword highlighting and pop/fade/slide entry.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Caption, CaptionStyle } from "../schemas/props";
import { isHighlighted, splitCaptionLines } from "../schemas/timeline";

export const HighlightedCaption: React.FC<{
  caption: Caption;
  style: CaptionStyle;
  top: number;
  fontFamily: string;
}> = ({ caption, style, top, fontFamily }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const local = frame - caption.startFrame;
  const scale = width / 1080;
  const fontSize = Math.round(style.fontSize * scale);
  const enter = spring({ frame: local, fps, config: { damping: 12, stiffness: 180 } });
  let transform = "none";
  let opacity = 1;
  if (style.animation === "pop") transform = `scale(${0.7 + 0.3 * enter})`;
  if (style.animation === "slide") transform = `translateY(${(1 - enter) * 80 * scale}px)`;
  if (style.animation === "fade") opacity = interpolate(local, [0, 6], [0, 1], { extrapolateRight: "clamp" });
  const lines = splitCaptionLines(caption.text, style.maxWordsPerLine);
  const outline = Math.round(style.outlineWidth * scale);
  const shadow = outline
    ? `0 0 ${outline}px ${style.outlineColor}, ${outline / 2}px ${outline / 2}px 0 ${style.outlineColor}`
    : "none";
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: Math.round(50 * scale),
        right: Math.round(50 * scale),
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        transform,
        opacity,
      }}
    >
      {lines.map((line, li) => (
        <div key={li} style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `0 ${fontSize * 0.25}px` }}>
          {line.split(" ").map((word, wi) => {
            const hl = isHighlighted(word, caption.highlights);
            // Highlighted words grow by up to 25% depending on emphasis intensity.
            const wscale = hl ? 1 + 0.25 * style.emphasis * enter : 1;
            return (
              <span
                key={wi}
                style={{
                  fontFamily,
                  // grow highlighted words via font size (not transform) so neighbours make room
                  fontSize: Math.round(fontSize * wscale),
                  fontWeight: 900,
                  lineHeight: 1.15,
                  color: hl ? style.highlightColor : style.color,
                  WebkitTextStroke: outline ? `${Math.max(2, outline / 2)}px ${style.outlineColor}` : undefined,
                  paintOrder: "stroke fill",
                  textShadow: shadow,
                  transform: `rotate(${hl ? -2 * style.emphasis : 0}deg)`,
                  display: "inline-block",
                  textTransform: style.uppercase ? "uppercase" : "none",
                }}
              >
                {word}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
};

