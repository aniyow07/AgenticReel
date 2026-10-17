// Single source of truth for composition IDs, shared by Root.tsx and the tests.
import type React from "react";
import type { RenderProps } from "../schemas/props";
import { MinecraftBrainrot } from "./MinecraftBrainrot";
import { OGVideo } from "./OGVideo";
import { SubwayBrainrot } from "./SubwayBrainrot";

export const COMPOSITIONS: Array<{ id: string; mode: RenderProps["mode"]; component: React.FC<RenderProps> }> = [
  { id: "OGVideo", mode: "og", component: OGVideo },
  { id: "MinecraftBrainrot", mode: "minecraft", component: MinecraftBrainrot },
  { id: "SubwayBrainrot", mode: "subway", component: SubwayBrainrot },
];
