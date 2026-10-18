// More scene backgrounds, each a different shape language (not just a recolour):
// aurora ribbons, a drifting constellation network, a pulsing honeycomb, circuit traces with travelling
// signals, expanding contour lines, sliding diagonal bands and falling code. All are frame-driven and seeded.
import React, { useMemo } from "react";
import { AbsoluteFill, random, useVideoConfig } from "remotion";
import type { Theme } from "../schemas/props";

const rgba = (hex: string, a: number) => {
  const n = parseInt(hex.replace("#", "").slice(0, 6), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

type P = { theme: Theme; t: number; seed: string };

export const Aurora: React.FC<P> = ({ theme, t }) => {
  const { width: W, height: H } = useVideoConfig();
  const bands = [theme.primary, theme.accent, theme.primary];
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0, filter: "blur(28px)" }}>
      {bands.map((c, k) => {
        const yb = H * (0.22 + k * 0.16);
        let top = `M 0 ${yb}`;
        let bottom = "";
        for (let x = 0; x <= W; x += W / 30) {
          const y = yb + H * 0.06 * Math.sin(x / (W * 0.35) + t * (0.35 + k * 0.12) + k * 2);
          top += ` L ${x} ${y}`;
          bottom = ` L ${x} ${y + H * (0.1 + 0.04 * Math.sin(t * 0.5 + x / W * 6 + k))}` + bottom;
        }
        return <path key={k} d={`${top}${bottom.replace(" L", " L")} Z`} fill={rgba(c, 0.32 - k * 0.06)} />;
      })}
    </svg>
  );
};

export const Constellation: React.FC<P> = ({ theme, t, seed }) => {
  const { width: W, height: H } = useVideoConfig();
  const pts = useMemo(
    () => new Array(42).fill(0).map((_, i) => ({
      x: random(`${seed}-cx${i}`), y: random(`${seed}-cy${i}`),
      vx: (random(`${seed}-cvx${i}`) - 0.5) * 0.02, vy: (random(`${seed}-cvy${i}`) - 0.5) * 0.02,
    })),
    [seed],
  );
  const wrap = (v: number) => ((v % 1) + 1) % 1;
  const pos = pts.map((p) => [wrap(p.x + p.vx * t) * W, wrap(p.y + p.vy * t) * H]);
  const link = Math.min(W, H) * 0.3;
  const lines = [];
  for (let i = 0; i < pos.length; i++) {
    for (let j = i + 1; j < pos.length; j++) {
      const d = Math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]);
      if (d < link) {
        lines.push(<line key={`${i}-${j}`} x1={pos[i][0]} y1={pos[i][1]} x2={pos[j][0]} y2={pos[j][1]}
          stroke={rgba(theme.primary, 0.6 * (1 - d / link))} strokeWidth={2.5} />);
      }
    }
  }
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      {lines}
      {pos.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i % 5 === 0 ? 7 : 4} fill={rgba(i % 5 === 0 ? theme.accent : theme.text, 0.7)} />
      ))}
    </svg>
  );
};

export const HexGrid: React.FC<P> = ({ theme, t }) => {
  const { width: W, height: H } = useVideoConfig();
  const r = W * 0.075;
  const w = Math.sqrt(3) * r;
  const cells = [];
  let k = 0;
  for (let row = -1; row * 1.5 * r < H + r; row++) {
    for (let col = -1; col * w < W + w; col++) {
      const cx = col * w + (row % 2 ? w / 2 : 0);
      const cy = row * 1.5 * r;
      const d = Math.hypot(cx - W / 2, cy - H * 0.45) / Math.max(W, H);
      const pulse = Math.max(0, Math.sin(t * 1.6 - d * 14));
      const pts = new Array(6).fill(0).map((_, i) => {
        const a = Math.PI / 6 + (i * Math.PI) / 3;
        return `${cx + r * 0.92 * Math.cos(a)},${cy + r * 0.92 * Math.sin(a)}`;
      }).join(" ");
      cells.push(<polygon key={k++} points={pts} fill={rgba(theme.accent, 0.18 * pulse ** 3)}
        stroke={rgba(theme.primary, 0.12 + 0.3 * pulse)} strokeWidth={2} />);
    }
  }
  return <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>{cells}</svg>;
};

export const Circuit: React.FC<P> = ({ theme, t, seed }) => {
  const { width: W, height: H } = useVideoConfig();
  const traces = useMemo(() => new Array(14).fill(0).map((_, i) => {
    // an L-shaped or Z-shaped trace on a grid
    const g = W / 12;
    const x0 = Math.floor(random(`${seed}-tx${i}`) * 12) * g;
    const y0 = Math.floor(random(`${seed}-ty${i}`) * 20) * g;
    const dx = (Math.floor(random(`${seed}-tdx${i}`) * 5) + 2) * g * (random(`${seed}-ts${i}`) > 0.5 ? 1 : -1);
    const dy = (Math.floor(random(`${seed}-tdy${i}`) * 6) + 2) * g;
    const pts: [number, number][] = [[x0, y0], [x0 + dx, y0], [x0 + dx, y0 + dy], [x0 + dx * 1.5, y0 + dy]];
    const len = pts.slice(1).reduce((s, p, k) => s + Math.hypot(p[0] - pts[k][0], p[1] - pts[k][1]), 0);
    return { pts, len, speed: 0.15 + random(`${seed}-tv${i}`) * 0.25, off: random(`${seed}-to${i}`) };
  }), [seed, W]);
  const at = (pts: [number, number][], f: number, len: number) => {
    let d = f * len;
    for (let k = 1; k < pts.length; k++) {
      const seg = Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]);
      if (d <= seg) {
        const q = d / seg;
        return [pts[k - 1][0] + (pts[k][0] - pts[k - 1][0]) * q, pts[k - 1][1] + (pts[k][1] - pts[k - 1][1]) * q];
      }
      d -= seg;
    }
    return pts[pts.length - 1];
  };
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      {traces.map((tr, i) => {
        const [px, py] = at(tr.pts, (tr.off + t * tr.speed) % 1, tr.len);
        return (
          <g key={i}>
            <polyline points={tr.pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={rgba(theme.primary, 0.28)} strokeWidth={3} />
            <circle cx={tr.pts[0][0]} cy={tr.pts[0][1]} r={7} fill="none" stroke={rgba(theme.primary, 0.5)} strokeWidth={3} />
            <circle cx={tr.pts[3][0]} cy={tr.pts[3][1]} r={6} fill={rgba(theme.primary, 0.5)} />
            <circle cx={px} cy={py} r={6} fill={theme.accent} style={{ filter: `drop-shadow(0 0 8px ${theme.accent})` }} />
          </g>
        );
      })}
    </svg>
  );
};

export const Contours: React.FC<P> = ({ theme, t, seed }) => {
  const { width: W, height: H } = useVideoConfig();
  const cx = W * (0.3 + 0.4 * random(`${seed}-ccx`));
  const cy = H * (0.3 + 0.3 * random(`${seed}-ccy`));
  const rings = [];
  for (let i = 0; i < 14; i++) {
    const f = ((i / 14 + t * 0.05) % 1);
    const r = f * Math.max(W, H) * 0.9;
    let d = "";
    for (let a = 0; a <= 64; a++) {
      const ang = (a / 64) * Math.PI * 2;
      const wob = 1 + 0.08 * Math.sin(ang * 3 + i + t * 0.4) + 0.05 * Math.sin(ang * 5 - t * 0.3);
      d += `${a ? "L" : "M"} ${cx + r * wob * Math.cos(ang)} ${cy + r * wob * Math.sin(ang)} `;
    }
    rings.push(<path key={i} d={`${d}Z`} fill="none" stroke={rgba(i % 3 ? theme.primary : theme.accent, 0.4 * (1 - f))} strokeWidth={2.5} />);
  }
  return <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>{rings}</svg>;
};

export const Stripes: React.FC<P> = ({ theme, t }) => {
  const shift = (t * 60) % 240;
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <div style={{
        position: "absolute", left: "-50%", top: "-50%", width: "200%", height: "200%",
        background: `repeating-linear-gradient(-35deg, ${rgba(theme.primary, 0.14)} 0 70px, transparent 70px 120px, ${rgba(theme.accent, 0.12)} 120px 150px, transparent 150px 240px)`,
        transform: `translateX(${shift}px)`,
      }} />
      <AbsoluteFill style={{ background: `linear-gradient(180deg, ${rgba(theme.background, 0.9)}, transparent 30%, transparent 70%, ${rgba(theme.background, 0.9)})` }} />
    </AbsoluteFill>
  );
};

const GLYPHS = "01ABCDEF<>/{}[]#$%=+*";

export const Matrix: React.FC<P> = ({ theme, t, seed }) => {
  const { width: W, height: H } = useVideoConfig();
  const size = W / 22;
  const cols = useMemo(() => new Array(22).fill(0).map((_, i) => ({
    speed: 0.25 + random(`${seed}-ms${i}`) * 0.5, off: random(`${seed}-mo${i}`), len: 6 + Math.floor(random(`${seed}-ml${i}`) * 10),
  })), [seed]);
  const rows = Math.ceil(H / size) + 1;
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0, fontFamily: "Consolas, monospace" }}>
      {cols.map((c, i) => {
        const head = ((c.off + t * c.speed) % 1.4) * rows;
        const out = [];
        for (let k = 0; k < c.len; k++) {
          const row = Math.floor(head) - k;
          if (row < 0 || row > rows) continue;
          const ch = GLYPHS[Math.floor(random(`${seed}-g${i}-${row}-${Math.floor(t * 4)}`) * GLYPHS.length)];
          out.push(<text key={k} x={i * size + size * 0.2} y={row * size} fontSize={size * 0.8}
            fill={k === 0 ? theme.text : rgba(theme.primary, 0.75 * (1 - k / c.len))}>{ch}</text>);
        }
        return <g key={i}>{out}</g>;
      })}
    </svg>
  );
};
