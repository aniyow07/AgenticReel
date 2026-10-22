import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { AnimatedTitle } from "../components/AnimatedTitle";
import { SceneBackdrop } from "../components/SceneBackdrop";
import { AudioLayer } from "../components/AudioLayer";
import { Caption } from "../components/Caption";
import { EndCard } from "../components/EndCard";
import {
  BarChart,
  Comparison,
  ImageScene,
  KeyPoints,
  ManimClip,
  ProcessDiagram,
  StatCounter,
  TextReveal,
  TimelineScene,
} from "../components/OGScenes";
import { ProgressIndicator } from "../components/ProgressIndicator";
import { SceneTransition } from "../components/SceneTransition";
import type { RenderProps, Scene, Theme } from "../schemas/props";
import { activeCaption } from "../schemas/timeline";
import { OG_THEME } from "../styles/theme";

const SceneBody: React.FC<{ scene: Scene; theme: Theme }> = ({ scene, theme }) => {
  switch (scene.visualType) {
    case "title":
      return <AnimatedTitle title={scene.params.title} subtitle={scene.params.subtitle} theme={theme} backdrop={scene.backdrop} />;
    case "text_reveal":
      return <TextReveal params={scene.params} theme={theme} />;
    case "key_points":
      return <KeyPoints params={scene.params} theme={theme} />;
    case "stat":
      return <StatCounter params={scene.params} theme={theme} />;
    case "timeline":
      return <TimelineScene params={scene.params} theme={theme} />;
    case "process":
      return <ProcessDiagram params={scene.params} theme={theme} />;
    case "comparison":
      return <Comparison params={scene.params} theme={theme} />;
    case "chart":
      return <BarChart params={scene.params} theme={theme} />;
    case "image":
      return <ImageScene params={scene.params} theme={theme} />;
    case "manim":
      return <ManimClip params={scene.params} theme={theme} />;
    case "end_card":
      return <EndCard text={scene.params.text} cta={scene.params.cta} theme={theme} />;
  }
};

export const OGVideo: React.FC<RenderProps> = (props) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const theme = props.theme.name === "default" ? OG_THEME : props.theme;
  const cap = props.showCaptions ? activeCaption(props.captions, frame) : null;
  const portrait = height > width;
  const safeBottom = portrait ? props.safeZone.bottom : Math.round(height * 0.08);
  const captionSize = Math.max(Math.round((48 * width) / 1080), Math.round(props.captionStyle.fontSize * 0.7 * (width / 1080)));
  return (
    <AbsoluteFill style={{ fontFamily: theme.fontFamily, color: theme.text }}>
      <AbsoluteFill style={{ backgroundColor: theme.background }} />
      {props.scenes.map((scene, i) => (
        // each backdrop overlaps the next scene by 12 frames so the next one can fade in over it
        <Sequence key={`bg-${scene.id}`} from={scene.startFrame}
          durationInFrames={scene.durationInFrames + (i < props.scenes.length - 1 ? 12 : 0)}>
          <SceneBackdrop theme={theme} seed={props.title || "agentreel"} style={scene.backdrop} sceneIndex={i}
            durationInFrames={scene.durationInFrames} fadeIn={i > 0} />
        </Sequence>
      ))}
      {props.scenes.map((scene) => (
        <Sequence key={scene.id} from={scene.startFrame} durationInFrames={scene.durationInFrames} name={scene.id}>
          <SceneTransition type={scene.transition} durationInFrames={scene.durationInFrames}>
            <AbsoluteFill
              style={{
                justifyContent: "center",
                alignItems: "center",
                paddingTop: portrait ? props.safeZone.top : 0,
                paddingBottom: portrait ? safeBottom + captionSize * 3 : captionSize * 2,
              }}
            >
              <SceneBody scene={scene} theme={theme} />
            </AbsoluteFill>
          </SceneTransition>
        </Sequence>
      ))}
      {cap ? <Caption caption={cap} theme={theme} bottom={safeBottom} fontSize={captionSize} /> : null}
      {props.showProgress ? <ProgressIndicator color={theme.accent} top={portrait ? Math.round(props.safeZone.top * 0.5) : 30} /> : null}
      <AudioLayer props={props} />
    </AbsoluteFill>
  );
};
