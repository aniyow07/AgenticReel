// Voice names and the voice <select> options, grouped by accent.
import { $$, esc } from '../core/dom.js';
import { api } from '../core/api.js';
import { state } from '../state.js';

export function voiceName(id) {
  if (!id) return state.info ? voiceName(state.info.default_voice) : 'Default voice';
  const p = id.replace('Neural', '').replace(/(Multilingual|Expressive)$/, '').split('-');
  return p.length >= 3 ? p[p.length - 1] : id;
}

export function voiceOptions(selected) {
  const def = state.info ? voiceName(state.info.default_voice) : 'Aria';
  let html = '<option value="">' + esc(def) + ' (default)</option>';
  let group = null;
  (state.voices || []).forEach((v) => {
    if (v.accent !== group) {
      html += (group ? '</optgroup>' : '') + '<optgroup label="' + esc(v.accent) + ' accent">';
      group = v.accent;
    }
    html += '<option value="' + esc(v.id) + '"' + (v.id === selected ? ' selected' : '') + '>' +
      esc(v.label.split(' · ')[0] + (v.gender ? ' · ' + v.gender.toLowerCase() : '')) + '</option>';
  });
  return html + (group ? '</optgroup>' : '');
}

// The voice list comes from Microsoft's service, so it loads after the page and fills any open pickers.
export function loadVoices() {
  api('/api/voices').then((v) => {
    state.voices = v;
    $$('select[data-voices]').forEach((sel) => { const cur = sel.value; sel.innerHTML = voiceOptions(cur); sel.value = cur; });
  }).catch(() => {});
}
