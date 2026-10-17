// Formatting for durations, dates, titles and file names.

export function fmtDur(s) {
  if (!s && s !== 0) return '';
  s = Math.round(s);
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

export function when(ts) {
  if (!ts) return '';
  const d = new Date(ts); const now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff === 0) return 'Today ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diff === 1) return 'Yesterday';
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}

export function title(t) { return t && t.length > 90 ? t.slice(0, 89) + '…' : (t || 'Untitled'); }

// A name that is safe as a Windows file name.
export function fileBase(t) {
  return (t || 'video').replace(/[<>:"\/\\|?*\x00-\x1f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 100) || 'video';
}
