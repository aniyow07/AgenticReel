// The Attach button and one chip per attached (or uploading) file, inside the brief box.
import { esc } from '../core/dom.js';
import { icon } from '../core/icons.js';

export function fileChips(files) {
  return '<button type="button" class="btn" id="attach" aria-label="Attach a PDF, DOCX, TXT or MD file">' + icon.clip + ' Attach</button>' +
    files.map((x, i) => x.busy
      ? '<span class="chip busy">' + icon.file + ' Uploading ' + esc(x.name) + '…</span>'
      : '<span class="chip">' + icon.file + '<span>' + esc(x.name) + '</span>' +
        (x.pages ? '<span class="meta">' + x.pages + (x.pages === 1 ? ' page' : ' pages') + '</span>' : '') +
        '<button type="button" data-rm="' + i + '" aria-label="Remove ' + esc(x.name) + '">' + icon.x + '</button></span>').join('');
}
