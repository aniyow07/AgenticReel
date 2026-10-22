// Shared app state. Screens read and write it; nothing here touches the DOM.

export const state = {
  info: null, // /api/info: provider, model, default voice, which styles have footage
  voicesBy: null, // /api/voices for each engine (chatterbox, edge), loaded in the background
  jobs: [], // /api/jobs, refreshed on a timer
  form: {
    topic: '', files: [], mode: 'og', duration: 45, format: 'video_9x16', content_type: 'factual_explainer',
    voice: '', tts_engine: '', speed: 10, motion: 'auto', audience: '', tone: '', language: 'English', subtitle_language: '',
    must: '', avoid: '', cta: '', exec_mode: '', quick_test: false, seed: 42, fresh_script: false, wikipedia: null, gpu: '', adv: false,
  },
  lib: { tab: 'all', q: '' },
};
