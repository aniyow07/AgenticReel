// Studio preview props. Real renders always receive --props from Python.
import type { RenderProps } from "./schemas/props";

export const makeDefaultProps = (mode: RenderProps["mode"]): RenderProps => ({
  mode,
  fps: 30,
  width: 1080,
  height: 1920,
  durationInFrames: 150,
  title: "AgentReel preview",
  narration: null,
  music: null,
  captions: [{ id: "c1", text: "AgentReel preview caption", startFrame: 0, endFrame: 150, highlights: ["AgentReel"], motion: 1 }],
  captionStyle: {
    fontSize: 72,
    color: "#FFFFFF",
    highlightColor: "#FFE135",
    outlineColor: "#000000",
    outlineWidth: 8,
    position: "center",
    animation: "pop",
    emphasis: 0.6,
    uppercase: true,
    maxWordsPerLine: 4,
  },
  showCaptions: true,
  scenes:
    mode === "og"
      ? [
          {
            id: "s1",
            startFrame: 0,
            durationInFrames: 150,
            transition: "fade",
            backdrop: "orbs",
            visualType: "title",
            params: { title: "AgentReel", subtitle: "Studio preview" },
          },
        ]
      : [],
  // Brainrot previews need a staged gameplay clip; Studio will show the validation error until one exists.
  background: mode === "og" ? [] : [{ src: `gameplay/${mode}.mp4`, startFrame: 0, durationInFrames: 150, trimBeforeFrames: 0 }],
  showProgress: true,
  zoomEffects: true,
  motionIntensity: 1,
  theme: {
    name: "default",
    background: "#0B1020",
    surface: "#151C33",
    primary: "#7C9CFF",
    accent: "#FFB547",
    text: "#F5F7FF",
    mutedText: "#A9B2D0",
    fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
  },
  safeZone: { top: 250, bottom: 350 },
});
