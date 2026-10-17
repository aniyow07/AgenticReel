// The red box of problems shown under a form (#errors).
import { $, esc } from '../core/dom.js';

export function showErrors(list) {
  const el = $('#errors');
  if (!el) return;
  el.hidden = !list || !list.length;
  el.innerHTML = (list || []).map((x) => '<li>' + esc(x) + '</li>').join('');
}

export function errorList(items) {
  return items.length ? '<ul class="errors">' + items.map((x) => '<li>' + esc(x) + '</li>').join('') + '</ul>' : '';
}
