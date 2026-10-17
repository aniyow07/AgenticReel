// The top bar: active nav link, AI provider label, "n rendering" pill, and the dark/light switch.
import { $, $$ } from '../core/dom.js';
import { state } from '../state.js';

function applyThemeLabel() {
  const dark = document.documentElement.dataset.theme !== 'light';
  const b = $('#theme');
  b.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  b.title = b.getAttribute('aria-label');
}

export function initTheme() {
  $('#theme').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('agentreel-theme', next); } catch (e) { /* private mode */ }
    applyThemeLabel();
  });
  applyThemeLabel();
}

export function renderHeader(routeName) {
  $$('[data-nav]').forEach((a) => a.classList.toggle('on', a.dataset.nav === routeName));
  $$('[data-nav]').forEach((a) => (a.dataset.nav === routeName ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  if (state.info) {
    const m = $('#model');
    m.textContent = state.info.provider + ' · ' + state.info.model + (state.info.has_key ? '' : ' · no API key');
    m.classList.toggle('warn', !state.info.has_key);
  }
  const running = state.jobs.filter((j) => j.status === 'running');
  const q = $('#queue');
  q.hidden = running.length === 0;
  if (running.length) {
    $('#queue-text').textContent = running.length + ' rendering';
    q.setAttribute('href', '/job/' + running[0].id);
  }
}
