// A yes/no confirmation using the <dialog id="confirm"> in index.html. Resolves true on OK.
import { $ } from '../core/dom.js';

export function confirmBox(heading, text, okLabel) {
  const dlg = $('#confirm');
  $('#confirm-title').textContent = heading;
  $('#confirm-text').textContent = text;
  $('#confirm-ok').textContent = okLabel;
  dlg.returnValue = '';
  dlg.showModal();
  $('#confirm-ok').focus();
  return new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true }));
}
