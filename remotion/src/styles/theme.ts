import type { Theme } from "../schemas/props";

export const OG_THEME: Theme = {
  name: "og",
  background: "#0B1020",
  surface: "#151C33",
  primary: "#7C9CFF",
  accent: "#FFB547",
  text: "#F5F7FF",
  mutedText: "#A9B2D0",
  fontFamily: "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
};

export const MINECRAFT_THEME: Theme = {
  name: "minecraft",
  background: "#1B2A12",
  surface: "#3B2A1A",
  primary: "#6ABE30",
  accent: "#FFE135",
  text: "#FFFFFF",
  mutedText: "#D7E4C0",
  fontFamily: "'Segoe UI Black', 'Arial Black', Impact, sans-serif",
};

export const SUBWAY_THEME: Theme = {
  name: "subway",
  background: "#0E1A2B",
  surface: "#16324F",
  primary: "#FF3D7F",
  accent: "#2BF0FF",
  text: "#FFFFFF",
  mutedText: "#C9E9FF",
  fontFamily: "'Segoe UI Black', 'Arial Black', Impact, sans-serif",
};

// Scales a size designed for 1080px width to the actual composition width.
export const scaleFor = (width: number) => (px: number) => Math.round((px * width) / 1080);
