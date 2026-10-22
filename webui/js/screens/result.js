// Result: the finished video, downloads, versions, "try another style", and script/sources/checks.
import { $, $$, app, esc } from '../core/dom.js';
import { post } from '../core/api.js';
import { fmtDur } from '../core/format.js';
import { icon } from '../core/icons.js';
import { styleName } from '../config.js';
import { go } from '../router.js';
import { deleteJob, refreshJobs, versionsOf } from '../services/jobs.js';
import { voiceName } from '../services/voices.js';
import { saveAs } from '../services/download.js';
import { toast } from '../ui/toast.js';
import { selectTile, styleTiles } from '../components/styleTiles.js';
import { engineOf, engineSwitch, voiceSelect } from '../components/voiceSelect.js';
import { defaultEngine } from '../services/voices.js';
import { disclosure, wireDisclosures } from '../components/disclosure.js';
import { titleEditor, wireTitleEditor } from '../components/titleEditor.js';
import { versionStrip } from '../components/versionStrip.js';
import { errorList, showErrors } from '../components/errorList.js';

const REVIEW_TEXT = {
  approved: 'An AI review approved the content.',
  needs_changes: 'An AI review suggested changes.',
  not_reviewed: 'No AI review of the content was run.',
};

function checksSummary(qa) {
  if (!qa) return '';
  if (!qa.passed) return 'some checks failed';
  if (qa.ok === qa.total) return 'all ' + qa.total + ' checks passed';
  const notes = qa.total - qa.ok;
  return 'checks passed, ' + notes + (notes === 1 ? ' note' : ' notes');
}

function factsLine(d) {
  return [fmtDur(d.duration_s), styleName(d.mode), voiceName(d.brief && d.brief.voice, d.brief && d.brief.tts_engine), d.size_mb ? d.size_mb + ' MB' : '',
    checksSummary(d.qa), d.is_test ? 'quick test' : ''].filter(Boolean).join(' · ');
}

function details(d) {
  const sources = d.facts.length
    ? '<ol class="lines">' + d.facts.map((x) => '<li>' + esc(x.claim) + '<br><span class="hint">' +
        esc([x.source, x.page ? 'page ' + x.page : '', (x.status || '').replace(/_/g, ' ')].filter(Boolean).join(' · ')) + '</span></li>').join('') + '</ol>'
    : '<p class="hint">No outside facts were used for this video.</p>';
  const checks = d.qa
    ? (d.qa.failed.length
        ? '<ol class="lines">' + d.qa.failed.map((c) => '<li>' + esc(c.name) + ' <span class="hint">' + esc(c.detail) + '</span></li>').join('') + '</ol>'
        : '<p class="hint">Every technical check passed: format, sync, captions, loudness, length and sources.</p>') +
      '<p class="hint">' + (REVIEW_TEXT[d.qa.review] || '') + '</p>'
    : '';
  return disclosure('script', 'Script', d.script.length + ' lines', '<ol class="lines">' + d.script.map((l) => '<li>' + esc(l) + '</li>').join('') + '</ol>') +
    disclosure('sources', 'Sources', d.facts.length ? d.facts.length + ' facts' : 'none', sources) +
    (d.qa ? disclosure('checks', 'Checks', d.qa.ok + ' of ' + d.qa.total + ' passed', checks) : '');
}

export function renderResult(d) {
  const wide = d.brief && d.brief.format === 'video_16x9';
  const errs = d.qa ? d.qa.failed.filter((c) => c.severity === 'error').map((c) => c.name + ': ' + c.detail) : [];
  const versions = versionsOf(d);
  // the engine this video was made with (older videos only have an Edge voice name), so a new version keeps it
  const b = d.brief || {};
  const eng = b.tts_engine || (/Neural$/.test(b.voice || '') ? 'edge' : defaultEngine());
  app.innerHTML =
    '<div class="page">' +
      '<section class="section" style="gap:10px">' + titleEditor(d.title) + '<p class="facts">' + esc(factsLine(d)) + '</p></section>' +
      errorList(errs) +
      '<section class="split" style="align-items:flex-end" aria-label="Video">' +
        '<div class="player' + (wide ? ' wide' : '') + '"><video controls playsinline preload="metadata" poster="/api/jobs/' + d.id + '/poster" src="/api/jobs/' + d.id + '/video"></video></div>' +
        '<div class="actions" style="padding-bottom:4px">' +
          '<button type="button" class="btn primary big block" id="dl">' + icon.down + ' Download video</button>' +
          '<div class="pair"><button type="button" class="btn" id="dlsrt">Captions file</button><button type="button" class="btn" id="folder">Open folder</button></div>' +
          '<button type="button" class="btn danger block" id="del">' + icon.trash + (versions.length > 1 ? ' Delete this version' : ' Delete video') + '</button>' +
          versionStrip(versions, d.id) +
        '</div>' +
      '</section>' +

      '<section class="section" aria-labelledby="h-again">' +
        '<div style="display:flex;flex-direction:column;gap:4px"><h2 id="h-again">Try another style</h2><p class="hint">Keeps the same script, so only the visuals and voice change.</p></div>' +
        styleTiles(d.mode, true) +
        '<div style="display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px;justify-content:space-between">' +
          '<div class="field"><span class="label">Voices</span>' + engineSwitch('v2', eng) + '</div>' +
          '<div class="field"><label for="v2">Voice</label>' + voiceSelect('v2', d.brief ? d.brief.voice : '', eng) + '</div>' +
          '<button type="button" class="btn primary" id="version">Make new version</button>' +
        '</div>' +
        '<ul class="errors" id="errors" hidden></ul>' +
      '</section>' +
      details(d) +
    '</div>';
  wire(d, versions);
}

function wire(d, versions) {
  let mode = d.mode;
  $$('.tile').forEach((t) => t.addEventListener('click', () => { mode = t.dataset.style; selectTile(mode); }));

  $('#folder').addEventListener('click', () => post('/api/jobs/' + d.id + '/open-folder').catch(() => {}));
  $('#dl').addEventListener('click', () => saveAs('/api/jobs/' + d.id + '/video', d.title, '.mp4', 'video/mp4', 'MP4 video'));
  $('#dlsrt').addEventListener('click', () => saveAs('/api/jobs/' + d.id + '/captions', d.title, '.srt', 'text/plain', 'Captions'));

  wireTitleEditor(() => d.title, async (text) => {
    try {
      const res = await post('/api/jobs/' + d.id + '/rename', { title: text });
      d.title = res.title;
      refreshJobs();
      return res.title;
    } catch (err) { toast((err.errors || ['Could not rename.'])[0]); return null; }
  });

  $('#del').addEventListener('click', async () => {
    const v = $('.player video');
    if (v) { v.pause(); v.removeAttribute('src'); v.load(); } // let go of the file so the folder can move
    const gone = await deleteJob({ id: d.id, title: d.title, versions: 1 }, false);
    if (!gone) { if (v) { v.src = '/api/jobs/' + d.id + '/video'; } return; }
    const next = versions.find((x) => x.id !== d.id);
    go(next ? '/job/' + next.id : '/library', true);
  });

  $('#version').addEventListener('click', async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try {
      const res = await post('/api/jobs/' + d.id + '/version', { mode: mode, voice: $('#v2').value, tts_engine: engineOf('v2') });
      refreshJobs();
      go('/job/' + res.id);
    } catch (err) { showErrors(err.errors); b.disabled = false; }
  });

  wireDisclosures(app);
}
