// The "Recent" row at the bottom of Create: the five newest finished videos.
import { esc } from '../core/dom.js';
import { fmtDur } from '../core/format.js';
import { styleShort } from '../config.js';

export function recentStrip(jobs) {
  return jobs.map((j) =>
    '<a href="/job/' + j.id + '" data-link><img class="thumb" loading="lazy" src="/api/jobs/' + j.id + '/poster" alt="">' +
    '<span class="t">' + esc(j.title) + '</span><span class="s">' + esc(styleShort(j.mode)) + ' · ' + fmtDur(j.duration_s) + '</span></a>').join('');
}
