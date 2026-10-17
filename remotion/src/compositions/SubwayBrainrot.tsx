import React from "react";
import type { RenderProps } from "../schemas/props";
import { SUBWAY_THEME } from "../styles/theme";
import { BrainrotVideo } from "./BrainrotVideo";

export const SubwayBrainrot: React.FC<RenderProps> = (props) => (
  <BrainrotVideo props={props} theme={props.theme.name === "default" ? SUBWAY_THEME : props.theme} />
);
