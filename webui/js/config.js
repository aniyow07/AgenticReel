// Fixed choices the screens offer. Keys match the pipeline's brief fields.

export const STYLES = {
  og: { name: 'Motion graphics', short: 'Motion graphics', desc: 'Animated diagrams, charts and captions' },
  minecraft: { name: 'Minecraft parkour', short: 'Minecraft', desc: 'Gameplay with big punchy captions' },
  subway: { name: 'Subway runner', short: 'Subway', desc: 'Gameplay with big punchy captions' },
};

export const TYPES = [
  ['factual_explainer', 'Explainer'], ['fictional_story', 'Story'], ['educational_story', 'Story that teaches'],
  ['opinion_commentary', 'Opinion or roast'], ['general_entertainment', 'Just for fun'],
  ['promotional', 'Promo'], ['awareness', 'Awareness'],
];

export const LANGS = ['English', 'Hindi', 'Spanish', 'French', 'German', 'Portuguese', 'Japanese', 'Korean'];

export const MOTIONS = [['auto', 'Auto'], ['subtle', 'Subtle'], ['strong', 'Strong'], ['off', 'Off']];

// narration speed in percent relative to the voice's normal pace; the script length follows it
export const SPEEDS = [[-10, 'Slower'], [0, 'Normal'], [10, 'Fast'], [20, 'Faster']];

export const FORMATS = [['video_9x16', 'Vertical 9:16'], ['video_16x9', 'Wide 16:9']];

export const GPU_MODES = [
  ['', 'Default from settings'], ['auto', 'Auto, if an NVIDIA GPU works'], ['on', 'Always'], ['off', 'Off, CPU only'],
];

export const WRITING_MODES = [
  ['', 'Default from settings'], ['AI_PREFERRED', 'AI, fall back to local'],
  ['AI_REQUIRED', 'AI only'], ['LOCAL_ONLY', 'Local only, no API calls'],
];

export const lengthChoices = (quickTest) =>
  quickTest ? [[10, '10s'], [15, '15s'], [20, '20s']] : [[30, '30s'], [45, '45s'], [60, '60s']];

export const styleName = (mode) => (STYLES[mode] ? STYLES[mode].name : mode);
export const styleShort = (mode) => (STYLES[mode] ? STYLES[mode].short : mode);
