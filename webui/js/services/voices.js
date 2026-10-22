// Voice names and the voice <select> options, for both voice engines:
// chatterbox = Natural (local), edge = Classic (Microsoft's online voices).
import { $$, esc } from '../core/dom.js';
import { api } from '../core/api.js';
import { state } from '../state.js';

export const ENGINES = [['chatterbox', 'Natural'], ['edge', 'Classic · online']];

// The engine a new video uses unless the user picks one: TTS_ENGINE from the server.
export function defaultEngine() {
  return (state.info && state.info.tts_engine) || 'chatterbox';
}

function defaultVoice(engine) {
  const d = state.info && state.info.default_voices;
  return (d && d[engine]) || (engine === 'edge' ? 'en-US-AriaNeural' : 'default');
}

export function voiceName(id, engine) {
  if (!id) return voiceName(defaultVoice(engine || defaultEngine()), engine);
  const all = [].concat(...Object.values(state.voicesBy || {}));
  const v = all.find((x) => x.id === id);
  if (v) return v.label.split(' · ')[0];
  // Edge voice names, e.g. en-US-AriaNeural -> Aria
  const p = id.replace('Neural', '').replace(/(Multilingual|Expressive)$/, '').split('-');
  return p.length >= 3 ? p[p.length - 1] : id.charAt(0).toUpperCase() + id.slice(1);
}

export function voiceOptions(selected, engine) {
  const def = defaultVoice(engine);
  let html = '<option value="">' + esc(voiceName(def, engine)) + ' (default)</option>';
  let group = null;
  ((state.voicesBy || {})[engine] || []).forEach((v) => {
    if (v.id === def) return; // already the first option
    const g = v.accent || '';
    if (g !== group) {
      html += (group ? '</optgroup>' : '') + (g ? '<optgroup label="' + esc(g) + ' accent">' : '');
      group = g;
    }
    const label = engine === 'edge' ? v.label.split(' · ')[0] : v.label;
    html += '<option value="' + esc(v.id) + '"' + (v.id === selected ? ' selected' : '') + '>' +
      esc(label + (v.gender ? ' · ' + v.gender.toLowerCase() : '')) + '</option>';
  });
  return html + (group ? '</optgroup>' : '');
}

function refill(sel) {
  const cur = sel.value;
  sel.innerHTML = voiceOptions(cur, sel.dataset.engine);
  sel.value = [...sel.options].some((o) => o.value === cur) ? cur : '';
}

// Both lists load after the page (the Classic one comes from Microsoft's service) and fill any open pickers.
export function loadVoices() {
  state.voicesBy = state.voicesBy || {};
  ENGINES.forEach(([engine]) => {
    api('/api/voices?engine=' + engine).then((v) => {
      state.voicesBy[engine] = v;
      $$('select[data-voices][data-engine="' + engine + '"]').forEach(refill);
    }).catch(() => {});
  });
}

// Switching Natural / Classic refills that picker with the other engine's voices (the default voice is picked).
export function initEngineSwitch() {
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-engine-for] button[data-val]');
    if (!b) return;
    const wrap = b.closest('[data-engine-for]');
    wrap.querySelectorAll('button[data-val]').forEach((x) => x.setAttribute('aria-pressed', x === b));
    const sel = document.getElementById(wrap.dataset.engineFor);
    if (!sel || sel.dataset.engine === b.dataset.val) return;
    sel.dataset.engine = b.dataset.val;
    sel.innerHTML = voiceOptions('', b.dataset.val);
    sel.value = '';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
