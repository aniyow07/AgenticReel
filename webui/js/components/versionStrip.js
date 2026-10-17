// Small posters of every version of a video, on its result page.
import { esc } from '../core/dom.js';
import { styleShort } from '../config.js';
import { voiceName } from '../services/voices.js';

export function versionStrip(versions, currentId) {
  if (versions.length <= 1) return '';
  return '<div class="section" style="gap:10px;margin-top:14px"><span class="hint">Versions</span><div class="versions">' +
    versions.map((v) => '<a href="/job/' + v.id + '" data-link class="' + (v.id === currentId ? 'on' : '') + '">' +
      (v.has_video ? '<img loading="lazy" src="/api/jobs/' + v.id + '/poster" alt="">' : '<span class="ph"></span>') +
      '<span>' + esc(styleShort(v.mode)) + '<br>' + esc(voiceName(v.voice)) + '</span></a>').join('') + '</div></div>';
}
