// A video that failed or stopped part-way, with a button to continue it.
import { $, app, esc } from '../core/dom.js';
import { post } from '../core/api.js';
import { refreshJobs } from '../services/jobs.js';
import { errorList } from '../components/errorList.js';
import { viewJob } from './job.js';

export function renderFailed(d) {
  const stopped = d.status === 'interrupted';
  const errs = d.qa && d.qa.failed.length ? d.qa.failed.filter((c) => c.severity === 'error').map((c) => c.name + ': ' + c.detail) : [];
  app.innerHTML =
    '<div class="page">' +
      '<section class="section"><h1>' + (stopped ? 'This video stopped before it finished' : 'This video could not be made') + '</h1><p class="lead">' + esc(d.topic) + '</p></section>' +
      (d.error ? '<p class="notice bad">' + esc(d.error) + '</p>' : '') +
      errorList(errs) +
      '<div style="display:flex;flex-wrap:wrap;gap:10px">' +
        '<button type="button" class="btn primary" id="resume">' + (stopped ? 'Continue where it stopped' : 'Try again') + '</button>' +
        '<a class="btn" href="/create" data-link>Back to create</a>' +
      '</div>' +
      '<p class="hint">Finished steps are reused, so trying again only redoes what failed.</p>' +
    '</div>';
  $('#resume').addEventListener('click', async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try { await post('/api/jobs/' + d.id + '/resume'); refreshJobs(); viewJob(d.id); } catch (err) { b.disabled = false; alert((err.errors || []).join('\n')); }
  });
}
