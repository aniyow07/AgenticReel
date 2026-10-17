// Downloads with a real "Save as" window where the browser has one (Chrome, Edge).
import { fileBase } from '../core/format.js';
import { toast } from '../ui/toast.js';

export async function saveAs(url, base, ext, mime, label) {
  const name = fileBase(base) + ext;
  if (window.showSaveFilePicker) {
    let handle = null;
    try {
      handle = await window.showSaveFilePicker({ suggestedName: name, types: [{ description: label, accept: { [mime]: [ext] } }] });
    } catch (e) {
      if (e.name === 'AbortError') return; // the person closed the dialog
    }
    if (handle) {
      toast('Saving ' + handle.name + '…');
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await res.body.pipeTo(await handle.createWritable());
        toast('Saved ' + handle.name);
      } catch (e) { toast('Could not save the file. Try again.'); }
      return;
    }
  }
  // Browsers without a save dialog (Firefox, Safari): download with the video's name.
  const a = document.createElement('a');
  a.href = url + (url.includes('?') ? '&' : '?') + 'download&name=' + encodeURIComponent(fileBase(base));
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
