// A row of mutually exclusive buttons (Length, Format, Camera motion).
import { esc } from '../core/dom.js';

export function segmented(name, items, value) {
  return '<div class="seg" role="group" aria-label="' + esc(name) + '">' + items.map(([v, label]) =>
    '<button type="button" data-seg="' + esc(name) + '" data-val="' + esc(v) + '" aria-pressed="' + (String(v) === String(value)) + '">' +
    esc(label) + '</button>').join('') + '</div>';
}
