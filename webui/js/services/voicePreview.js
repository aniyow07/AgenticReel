// Plays a short sample of a voice (recorded once by the server with Edge TTS, then cached).
// One sample plays at a time; while it plays, picking another voice plays that one instead.
import { $ } from '../core/dom.js';
import { icon } from '../core/icons.js';
import { state } from '../state.js';
import { toast } from '../ui/toast.js';

const STOP = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
let audio = null;
let playingFor = null; // id of the <select> whose sample is playing

function setButton(selectId, mode) {
  const b = $('[data-voice-play="' + selectId + '"]');
  if (!b) return;
  b.innerHTML = mode === 'playing' ? STOP : icon.play;
  b.classList.toggle('busy', mode === 'loading');
  b.setAttribute('aria-label', mode === 'playing' ? 'Stop the voice sample' : 'Play a sample of this voice');
}

function stop() {
  if (audio) { audio.pause(); audio = null; }
  if (playingFor) setButton(playingFor, 'idle');
  playingFor = null;
}

function play(selectId) {
  const sel = $('#' + selectId);
  if (!sel) return;
  const voice = sel.value || (state.info && state.info.default_voice) || 'en-US-AriaNeural';
  const speed = Number(state.form.speed) || 0;
  stop();
  playingFor = selectId;
  setButton(selectId, 'loading');
  const a = new Audio('/api/voices/sample?voice=' + encodeURIComponent(voice) + '&speed=' + speed);
  audio = a;
  a.addEventListener('playing', () => { if (audio === a) setButton(selectId, 'playing'); });
  a.addEventListener('ended', () => { if (audio === a) stop(); });
  a.addEventListener('error', () => {
    if (audio !== a) return;
    stop();
    toast('Could not play a sample of that voice. Check your internet connection.');
  });
  a.play().catch(() => {});
}

export function initVoicePreview() {
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-voice-play]');
    if (!b) return;
    const id = b.dataset.voicePlay;
    if (playingFor === id) stop(); else play(id);
  });
  document.addEventListener('change', (e) => {
    if (e.target.matches('select[data-voices]') && playingFor === e.target.id) play(e.target.id);
  });
  // leaving the screen stops the sample
  window.addEventListener('popstate', stop);
  document.addEventListener('click', (e) => { if (e.target.closest('a[data-link]')) stop(); });
}
