// The small message at the bottom of the screen, with an optional action such as Undo.
import { $ } from '../core/dom.js';

let timer = null;

export function toast(text, actionLabel, action) {
  const el = $('#toast');
  $('#toast-text').textContent = text;
  const b = $('#toast-btn');
  b.hidden = !actionLabel;
  b.textContent = actionLabel || '';
  b.onclick = async () => { el.hidden = true; clearTimeout(timer); if (action) await action(); };
  el.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => { el.hidden = true; }, 10000);
}
