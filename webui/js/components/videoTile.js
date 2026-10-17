// One video in the Library wall: poster, title and length on the image, versions badge, trash button.
import { esc } from '../core/dom.js';
import { fmtDur, title } from '../core/format.js';
import { icon } from '../core/icons.js';
import { styleShort } from '../config.js';

// Posters that have finished loading once; redrawn tiles show them at once instead of fading in again.
const loadedPosters = new Set();

export function trackPosterLoads(wall) {
  wall.addEventListener('load', (e) => {
    const img = e.target;
    if (img.tagName !== 'IMG') return;
    img.classList.add('in');
    loadedPosters.add(img.getAttribute('src'));
  }, true);
}

export function newVideoTile() {
  return '<a href="/create" data-link class="newtile">' + icon.plus + 'New video</a>';
}

function posterImg(src) {
  return '<img loading="lazy" src="' + src + '" alt=""' + (loadedPosters.has(src) ? ' class="in"' : '') + '>';
}

export function videoTile(j) {
  const run = j.status === 'running';
  const label = run ? 'Rendering' : (j.has_video ? fmtDur(j.duration_s) : (j.status === 'interrupted' ? 'Stopped' : 'Failed'));
  return '<div class="vtw"><a href="/job/' + j.id + '" data-link class="vt' + (run ? ' dim' : '') + '" aria-label="' + esc(j.title + (run ? ', rendering' : '')) + '">' +
    (j.has_video ? posterImg('/api/jobs/' + j.id + '/poster') : '<span class="noimg">' + (run ? '' : esc(label)) + '</span>') +
    '<span class="scrim" aria-hidden="true"></span>' +
    (j.has_video && !run ? '<span class="play" aria-hidden="true">' + icon.play + '</span>' : '') +
    (j.versions > 1 ? '<span class="badge">' + icon.stack + j.versions + '</span>' : '') +
    '<span class="info"><span class="ttl">' + esc(title(j.title)) + '</span>' +
      '<span class="sub"><span>' + esc(styleShort(j.mode) + (j.is_test ? ' · test' : '')) + '</span><span>' + esc(run ? j.progress.pct + '%' : label) + '</span></span>' +
      (run ? '<span class="mini"><span style="width:' + j.progress.pct + '%"></span></span>' : '') +
    '</span></a>' +
    (run ? '' : '<button type="button" class="del" data-del="' + j.id + '" aria-label="Delete ' + esc(title(j.title)) + '" title="Delete">' + icon.trash + '</button>') +
    '</div>';
}
