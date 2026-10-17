// Rendering: live percentage, what is happening now, and the step pills. Polls until the job ends.
import { $, app, esc } from '../core/dom.js';
import { api } from '../core/api.js';
import { clearTimers, every } from '../core/timers.js';
import { refreshJobs } from '../services/jobs.js';
import { aiSkippedNotice, progressSteps } from '../components/progressSteps.js';
import { livePreview, startLivePreview } from '../components/livePreview.js';
import { renderResult } from './result.js';
import { renderFailed } from './failed.js';

export function renderRendering(d) {
  const p = d.progress;
  app.innerHTML =
    '<div class="page">' +
      '<section class="section"><h1>Making your video</h1><p class="lead">' + esc(d.topic) + '</p></section>' +
      '<section class="split" aria-label="Progress">' +
        livePreview(d) +
        '<div class="prog">' +
          '<div style="display:flex;flex-direction:column;gap:8px"><span class="pct" id="pct">' + p.pct + '%</span>' +
          '<span class="now"><span class="dot pulse" aria-hidden="true"></span><span id="now">' + esc(p.now) + '</span></span></div>' +
          '<div class="bar" role="progressbar" aria-label="Progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + p.pct + '" id="bar"><div style="width:' + p.pct + '%"></div></div>' +
          '<ol class="steps" id="steps" aria-label="Steps">' + progressSteps(p) + '</ol>' +
          '<div id="skipped">' + aiSkippedNotice(p) + '</div>' +
          '<p class="hint">You can leave this page. The video keeps rendering and shows up in your library.</p>' +
          '<div><a class="btn" href="/create" data-link>Make another</a></div>' +
        '</div>' +
      '</section>' +
    '</div>';
  const updatePreview = startLivePreview(d);
  every(1500, async () => {
    let n;
    try { n = await api('/api/jobs/' + d.id); } catch (e) { return; }
    if (n.status !== 'running') { clearTimers(); refreshJobs(); n.has_video ? renderResult(n) : renderFailed(n); return; }
    update(n.progress);
    updatePreview(n);
  });
}

function update(q) {
  $('#pct').textContent = q.pct + '%';
  $('#now').textContent = q.now;
  $('#bar').setAttribute('aria-valuenow', q.pct);
  $('#bar > div').style.width = q.pct + '%';
  $('#steps').innerHTML = progressSteps(q);
  $('#skipped').innerHTML = aiSkippedNotice(q);
}
