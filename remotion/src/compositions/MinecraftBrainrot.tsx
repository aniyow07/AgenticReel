import React from "react";
import type { RenderProps } from "../schemas/props";
import { MINECRAFT_THEME } from "../styles/theme";
import { BrainrotVideo } from "./BrainrotVideo";

export const MinecraftBrainrot: React.FC<RenderProps> = (props) => (
  <BrainrotVideo props={props} theme={props.theme.name === "default" ? MINECRAFT_THEME : props.theme} />
);
