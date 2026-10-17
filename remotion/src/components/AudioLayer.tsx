// Narration plus optional music. Music is ducked whenever a narration caption is active.
import React from "react";
import { Audio, staticFile } from "remotion";
import type { RenderProps } from "../schemas/props";
import { isSpeechActive } from "../schemas/timeline";

export const AudioLayer: React.FC<{ props: RenderProps }> = ({ props }) => {
  const { narration, music, captions } = props;
  return (
    <>
      {narration ? <Audio src={staticFile(narration.src)} volume={narration.volume} /> : null}
      {music ? (
        <Audio
          src={staticFile(music.src)}
          loop
          volume={(f) => (isSpeechActive(captions, f) ? music.duckedVolume : music.volume)}
        />
      ) : null}
    </>
  );
};
