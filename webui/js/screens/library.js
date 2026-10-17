// Library: search, style tabs and the wall of video tiles (one per group of versions).
import { $, app, esc } from '../core/dom.js';
import { every } from '../core/timers.js';
import { icon } from '../core/icons.js';
import { STYLES } from '../config.js';
import { state } from '../state.js';
import { currentRoute } from '../router.js';
import { deleteJob, groupHeads, refreshJobs } from '../services/jobs.js';
import { newVideoTile, trackPosterLoads, videoTile } from '../components/videoTile.js';

export function viewLibrary() {
  app.innerHTML =
    '<div class="page wide">' +
      '<div class="lib-head"><div><h1>Library</h1><div class="sub" id="lib-sub"></div></div>' +
        '<div class="search">' + icon.search + '<label for="q" class="sr">Search videos</label><input id="q" type="search" placeholder="Search your videos" value="' + esc(state.lib.q) + '"><kbd class="kbd-hint" aria-hidden="true">/</kbd></div>' +
      '</div>' +
      '<div class="tabs" role="tablist" aria-label="Style" id="tabs"></div>' +
      '<div class="wall" id="wall"></div>' +
      '<div class="empty" id="lib-empty" hidden><p style="margin:0;font-size:16px;font-weight:500">Nothing matches that</p><button type="button" class="btn" id="clear">Clear search</button></div>' +
    '</div>';
  $('#q').addEventListener('input', (e) => { state.lib.q = e.target.value; draw(); });
  $('#clear').addEventListener('click', () => { state.lib.q = ''; state.lib.tab = 'all'; $('#q').value = ''; draw(); });
  $('#tabs').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) { state.lib.tab = b.dataset.tab; draw(); } });
  trackPosterLoads($('#wall'));
  $('#wall').addEventListener('click', async (e) => {
    const b = e.target.closest('button[data-del]');
    if (!b) return;
    e.preventDefault();
    const job = state.jobs.find((j) => j.id === b.dataset.del);
    if (job && await deleteJob(job, true)) draw();
  });
  draw();
  refreshJobs().then(draw);
  every(3000, () => { if (state.jobs.some((j) => j.status === 'running')) refreshJobs().then(draw); });
}

function tabsHTML(heads) {
  const count = (k) => heads.filter((j) => k === 'all' || j.mode === k).length;
  return [['all', 'All']].concat(Object.keys(STYLES).map((k) => [k, STYLES[k].name])).map(([k, l]) =>
    '<button type="button" role="tab" data-tab="' + k + '" aria-selected="' + (state.lib.tab === k) + '">' + esc(l) + ' <span class="n">' + count(k) + '</span></button>').join('');
}

// While a video renders the wall is redrawn every few seconds. Replace only the tiles that changed,
// so the other posters are not reloaded and do not flicker.
const tileHTML = new WeakMap();

function patchWall(wall, tiles) {
  const kids = Array.from(wall.children);
  const sameOrder = kids.length === tiles.length && kids.every((el, i) => el.dataset.key === tiles[i][0]);
  if (!sameOrder) {
    wall.innerHTML = tiles.map(([, html]) => html).join('');
    Array.from(wall.children).forEach((el, i) => { el.dataset.key = tiles[i][0]; tileHTML.set(el, tiles[i][1]); });
    return;
  }
  kids.forEach((el, i) => {
    if (tileHTML.get(el) === tiles[i][1]) return;
    const tmp = document.createElement('div');
    tmp.innerHTML = tiles[i][1];
    const fresh = tmp.firstElementChild;
    fresh.dataset.key = tiles[i][0];
    tileHTML.set(fresh, tiles[i][1]);
    el.replaceWith(fresh);
  });
}

function draw() {
  if (currentRoute().name !== 'library' || !$('#wall')) return;
  const heads = groupHeads(state.jobs);
  const q = state.lib.q.trim().toLowerCase();
  const items = heads.filter((j) => (state.lib.tab === 'all' || j.mode === state.lib.tab) &&
    (!q || (j.title + ' ' + j.topic).toLowerCase().includes(q)));
  const running = state.jobs.filter((j) => j.status === 'running').length;
  const done = state.jobs.filter((j) => j.has_video).length;
  $('#tabs').innerHTML = tabsHTML(heads);
  $('#lib-sub').textContent = done + (done === 1 ? ' video' : ' videos') + (running ? ' · ' + running + ' rendering' : '');
  patchWall($('#wall'), (q ? [] : [['new', newVideoTile()]]).concat(items.map((j) => [j.id, videoTile(j)])));
  $('#lib-empty').hidden = items.length > 0 || !q;
}
