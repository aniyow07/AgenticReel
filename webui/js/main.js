// Entry point: load what the header needs, then start the router.
import { app } from './core/dom.js';
import { api } from './core/api.js';
import { state } from './state.js';
import { initRouter, currentRoute, route } from './router.js';
import { initTheme } from './ui/header.js';
import { initShortcuts } from './ui/shortcuts.js';
import { refreshJobs } from './services/jobs.js';
import { loadVoices } from './services/voices.js';
import { initVoicePreview } from './services/voicePreview.js';
import { handleCreateClick } from './screens/create.js';

async function boot() {
  initTheme();
  initRouter();
  initShortcuts();
  initVoicePreview();
  app.addEventListener('click', handleCreateClick);
  try { state.info = await api('/api/info'); } catch (e) { /* header stays empty */ }
  await refreshJobs();
  route();
  loadVoices();
  // keeps the "n rendering" pill current; the library refreshes on its own timer
  setInterval(() => { if (currentRoute().name !== 'library') refreshJobs(); }, 5000);
}

boot();
