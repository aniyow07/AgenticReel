// The video title with a pencil button that turns it into a text field for renaming.
import { $, esc } from '../core/dom.js';
import { icon } from '../core/icons.js';

export function titleEditor(text) {
  return '<div class="titlebar" id="titlebar"><h1 id="vtitle">' + esc(text) + '</h1>' +
      '<button type="button" class="icon-btn" id="rename" aria-label="Rename video" title="Rename">' + icon.pen + '</button></div>' +
    '<form class="titleedit" id="titleedit" hidden><label for="tname" class="sr">Video name</label>' +
      '<input id="tname" class="input" maxlength="120" value="' + esc(text) + '">' +
      '<button type="submit" class="btn primary">Save</button><button type="button" class="btn" id="tcancel">Cancel</button></form>';
}

// onSave(newText) returns the saved title (or throws); the heading updates to it.
export function wireTitleEditor(getTitle, onSave) {
  const bar = $('#titlebar'), form = $('#titleedit'), inp = $('#tname');
  const editing = (on) => { bar.hidden = on; form.hidden = !on; if (on) { inp.value = getTitle(); inp.focus(); inp.select(); } };
  $('#rename').addEventListener('click', () => editing(true));
  $('#tcancel').addEventListener('click', () => editing(false));
  inp.addEventListener('keydown', (e) => { if (e.key === 'Escape') editing(false); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const saved = await onSave(inp.value);
    if (saved) {
      $('#vtitle').textContent = saved;
      editing(false);
    }
  });
}
