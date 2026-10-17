import React from "react";
import { Composition } from "remotion";
import { COMPOSITIONS } from "./compositions/registry";
import { makeDefaultProps } from "./defaultProps";
import { RenderPropsSchema, type RenderProps } from "./schemas/props";

// Props are validated with Zod before rendering; the parsed (defaulted) props
// also drive duration, size and fps so Python stays the single timeline authority.
export const calculateMetadata = ({ props, compositionId }: { props: RenderProps; compositionId: string }) => {
  const parsed = RenderPropsSchema.parse(props);
  const entry = COMPOSITIONS.find((c) => c.id === compositionId);
  if (entry && entry.mode !== parsed.mode) {
    throw new Error(`Composition ${compositionId} expects mode "${entry.mode}" but props say "${parsed.mode}"`);
  }
  return {
    durationInFrames: parsed.durationInFrames,
    fps: parsed.fps,
    width: parsed.width,
    height: parsed.height,
    props: parsed,
  };
};

export const RemotionRoot: React.FC = () => (
  <>
    {COMPOSITIONS.map(({ id, mode, component }) => {
      const defaults = makeDefaultProps(mode);
      return (
        <Composition
          key={id}
          id={id}
          component={component}
          durationInFrames={defaults.durationInFrames}
          fps={defaults.fps}
          width={defaults.width}
          height={defaults.height}
          defaultProps={defaults}
          calculateMetadata={({ props }) => calculateMetadata({ props, compositionId: id })}
        />
      );
    })}
  </>
);
