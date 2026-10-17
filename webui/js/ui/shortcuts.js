// Keyboard shortcuts that work on every screen.
import { $ } from '../core/dom.js';

export function initShortcuts() {
  // "/" jumps to the library search, like most media apps
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
    const q = $('#q');
    if (q) { e.preventDefault(); q.focus(); }
  });
}
