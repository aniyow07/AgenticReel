// Tiny DOM helpers. Every value placed in HTML strings goes through esc().

export const app = document.getElementById('app');

export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const $ = (sel, el) => (el || document).querySelector(sel);
export const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
