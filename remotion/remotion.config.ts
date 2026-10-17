// Remotion CLI configuration. Python passes most options as explicit CLI flags,
// so this file only sets safe defaults for Studio and manual renders.
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setOverwriteOutput(true);
