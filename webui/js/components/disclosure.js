// A collapsible section ("More options", "Script", "Sources", "Checks").
import { $, $$, esc } from '../core/dom.js';
import { icon } from '../core/icons.js';

export function disclosure(id, label, meta, body) {
  return '<section class="disclosure"><button type="button" aria-expanded="false" aria-controls="d-' + id + '">' + icon.chev + ' ' + esc(label) +
    ' <span class="opt">' + esc(meta) + '</span></button><div id="d-' + id + '" hidden>' + body + '</div></section>';
}

export function wireDisclosures(root) {
  $$('.disclosure > button', root).forEach((b) => b.addEventListener('click', () => {
    const open = b.getAttribute('aria-expanded') !== 'true';
    b.setAttribute('aria-expanded', open);
    $('#' + b.getAttribute('aria-controls')).hidden = !open;
  }));
}
