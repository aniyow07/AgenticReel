// Shared brainrot renderer: real gameplay background + narration + big captions.
// Minecraft and Subway compositions only differ by theme and caption defaults.
import React from "react";
import { AbsoluteFill, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { AudioLayer } from "../components/AudioLayer";
import { HighlightedCaption } from "../components/HighlightedCaption";
import { ProgressIndicator } from "../components/ProgressIndicator";
import type { RenderProps, Theme } from "../schemas/props";
import { activeCaption, captionTop } from "../schemas/timeline";

const Gameplay: React.FC<{ props: RenderProps }> = ({ props }) => {
  const frame = useCurrentFrame();
  const cap = activeCaption(props.captions, frame);
  // Camera reaction per caption. The storyboard model rates each line calm/normal/strong/hit (caption.motion);
  // motionIntensity scales everything (0 = off). Constant push and sway keep the footage alive between lines.
  const sinceCaption = cap ? frame - cap.startFrame : 99;
  const I = props.zoomEffects ? props.motionIntensity : 0;
  const level = cap ? cap.motion : 0;
  // calm/normal lines get no punch at all; only lines the model marks strong/hit react
  const punchAmt = [0, 0, 0.07, 0.12][level] * I;
  const shakeDeg = [0, 0, 1.1, 2.6][level] * I;
  const shakeFrames = [1, 1, 10, 15][level];
  const pulse = 1 + interpolate(sinceCaption, [0, 8], [punchAmt, 0], { extrapolateRight: "clamp" });
  const push = 1 + I * (0.04 + 0.04 * Math.sin((frame / props.fps) * 0.35));
  const shake = interpolate(sinceCaption, [0, shakeFrames], [1, 0], { extrapolateRight: "clamp" });
  const rot = shake * shakeDeg * Math.sin(frame * 1.7) + I * 0.6 * Math.sin((frame / props.fps) * 0.5);
  const jolt = shake * shakeDeg * 0.6 * Math.cos(frame * 2.3); // small sideways jolt on strong/hit lines
  const panX = I * 1.5 * Math.sin((frame / props.fps) * 0.27) + jolt;
  return (
    <AbsoluteFill style={{ transform: `scale(${pulse * push}) rotate(${rot}deg) translateX(${panX}%)` }}>
      {props.background.map((seg, i) => (
        <Sequence key={i} from={seg.startFrame} durationInFrames={seg.durationInFrames}>
          <OffthreadVideo
            src={staticFile(seg.src)}
            muted
            trimBefore={seg.trimBeforeFrames}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

export const BrainrotVideo: React.FC<{ props: RenderProps; theme: Theme }> = ({ props, theme }) => {
  const frame = useCurrentFrame();
  const { height } = useVideoConfig();
  const cap = props.showCaptions ? activeCaption(props.captions, frame) : null;
  const top = captionTop(props.captionStyle.position, height, props.safeZone);
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Gameplay props={props} />
      {/* light vignette keeps white captions readable over bright gameplay */}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,0.45) 100%)" }} />
      {cap ? (
        <HighlightedCaption key={cap.id} caption={cap} style={props.captionStyle} top={top} fontFamily={theme.fontFamily} />
      ) : null}
      {props.showProgress ? <ProgressIndicator color={theme.accent} top={Math.round(props.safeZone.top * 0.5)} /> : null}
      <AudioLayer props={props} />
    </AbsoluteFill>
  );
};
