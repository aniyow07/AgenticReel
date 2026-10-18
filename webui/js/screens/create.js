// Create: the brief box, style cards, options and the Recent strip.
import { $, $$, app, esc } from '../core/dom.js';
import { api, post } from '../core/api.js';
import { icon } from '../core/icons.js';
import { FORMATS, LANGS, MOTIONS, SPEEDS, TYPES, WRITING_MODES, lengthChoices } from '../config.js';
import { state } from '../state.js';
import { go, currentRoute } from '../router.js';
import { groupHeads, refreshJobs } from '../services/jobs.js';
import { segmented } from '../components/segmented.js';
import { selectTile, styleTiles, wirePreviews } from '../components/styleTiles.js';
import { voiceSelect } from '../components/voiceSelect.js';
import { fileChips } from '../components/fileChips.js';
import { recentStrip } from '../components/recentStrip.js';
import { showErrors } from '../components/errorList.js';

const SEG_FIELD = { Length: 'duration', Format: 'format', 'Camera motion': 'motion', 'Voice speed': 'speed' };

const field = (id, label, control) => '<div class="field"><label for="' + id + '">' + label + '</label>' + control + '</div>';
const options = (items, selected) => items.map(([v, l]) => '<option value="' + v + '"' + (v === selected ? ' selected' : '') + '>' + esc(l) + '</option>').join('');
const langOptions = (selected) => LANGS.map((l) => '<option' + (l === selected ? ' selected' : '') + '>' + l + '</option>').join('');

function briefSection(f) {
  return '<section class="section" aria-labelledby="h-brief">' +
    '<h1 id="h-brief">What should the video explain?</h1>' +
    '<div class="box" id="box">' +
      '<label for="brief" class="sr">Brief</label>' +
      '<textarea id="brief" rows="4" maxlength="1000" placeholder="A topic, a question, or what to do with the file you attach">' + esc(f.topic) + '</textarea>' +
      '<div class="box-bar">' +
        '<div class="chips" id="chips"></div>' +
        '<button type="button" class="btn primary" id="go">Generate <span class="kbd">Ctrl ↵</span></button>' +
      '</div>' +
    '</div>' +
    '<input type="file" id="file" accept=".pdf,.docx,.txt,.md" multiple hidden>' +
    '<ul class="errors" id="errors" hidden></ul>' +
    '<p class="hint">Facts in the script come only from your brief and attached files. Anything it cannot source is left out.</p>' +
  '</section>';
}

function optionsSection(f) {
  return '<section class="options" aria-label="Options">' +
    '<div class="field"><span class="label">Length</span><div id="len">' + segmented('Length', lengthChoices(f.quick_test), f.duration) + '</div></div>' +
    '<div class="field"><span class="label">Format</span>' + segmented('Format', FORMATS, f.format) + '</div>' +
    '<div class="field"><label for="ctype">Type</label><select id="ctype" class="input">' + options(TYPES, f.content_type) + '</select></div>' +
    '<div class="field"><label for="voice">Voice</label>' + voiceSelect('voice', f.voice) + '</div>' +
    '<div class="field"><span class="label">Voice speed</span>' + segmented('Voice speed', SPEEDS, f.speed) + '</div>' +
    '<div class="field" id="motion-field"' + (f.mode === 'og' ? ' hidden' : '') + '><span class="label">Camera motion</span>' + segmented('Camera motion', MOTIONS, f.motion) + '</div>' +
  '</section>';
}

function moreOptions(f) {
  return '<section class="disclosure">' +
    '<button type="button" id="adv-btn" aria-expanded="' + f.adv + '" aria-controls="adv">' + icon.chev + ' More options <span class="opt">audience, tone, language, must-haves</span></button>' +
    '<div id="adv"' + (f.adv ? '' : ' hidden') + '>' +
      '<div class="grid2">' +
        field('aud', 'Audience', '<input id="aud" class="input" type="text" maxlength="200" placeholder="General audience" value="' + esc(f.audience) + '">') +
        field('tone', 'Tone', '<input id="tone" class="input" type="text" maxlength="200" placeholder="engaging, clear" value="' + esc(f.tone) + '">') +
        field('lang', 'Narration language', '<select id="lang" class="input">' + langOptions(f.language) + '</select>') +
        field('slang', 'Subtitle language', '<select id="slang" class="input"><option value="">Same as narration</option>' + langOptions(f.subtitle_language) + '</select>') +
        field('must', 'Must mention <span class="opt">one per line</span>', '<textarea id="must" class="input" rows="3">' + esc(f.must) + '</textarea>') +
        field('avoid', 'Avoid <span class="opt">one per line</span>', '<textarea id="avoid" class="input" rows="3">' + esc(f.avoid) + '</textarea>') +
        field('cta', 'Ending line <span class="opt">optional</span>', '<input id="cta" class="input" type="text" maxlength="200" placeholder="Follow for part 2" value="' + esc(f.cta) + '">') +
        field('ai', 'Writing', '<select id="ai" class="input">' + WRITING_MODES.map(([v, l]) => '<option value="' + v + '"' + (v === f.exec_mode ? ' selected' : '') + '>' + l + '</option>').join('') + '</select>') +
      '</div>' +
      '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px 28px;margin-top:16px">' +
        '<label class="check"><input type="checkbox" id="quick"' + (f.quick_test ? ' checked' : '') + '> Quick test render <span class="opt" style="color:var(--faint)">short, small, marked as a test</span></label>' +
        '<label class="check"><input type="checkbox" id="fresh"' + (f.fresh_script ? ' checked' : '') + '> Write a fresh script</label>' +
        '<label class="check">Seed <input id="seed" class="input" type="number" value="' + esc(f.seed) + '" style="width:90px;height:40px"></label>' +
      '</div>' +
    '</div>' +
  '</section>';
}

const recentSection = '<section class="section" id="recent-wrap" hidden aria-labelledby="h-recent">' +
  '<div class="row-between"><h2 id="h-recent">Recent</h2><a href="/library" data-link class="hint" style="color:var(--muted)">View all</a></div>' +
  '<div class="recent" id="recent"></div>' +
'</section>';

export function viewCreate() {
  const f = state.form;
  app.innerHTML = '<div class="page">' + briefSection(f) +
    '<section class="section" aria-labelledby="h-style"><h2 id="h-style">Style</h2>' + styleTiles(f.mode) + '</section>' +
    optionsSection(f) + moreOptions(f) + recentSection + '</div>';
  renderChips();
  renderRecent();
  wire();
  if (!f.topic) $('#brief').focus();
}

function renderChips() {
  const wrap = $('#chips');
  if (wrap) wrap.innerHTML = fileChips(state.form.files);
}

function renderRecent() {
  const heads = groupHeads(state.jobs).filter((j) => j.has_video).slice(0, 5);
  const wrap = $('#recent-wrap');
  if (!wrap) return;
  wrap.hidden = heads.length === 0;
  $('#recent').innerHTML = recentStrip(heads);
}

async function uploadFiles(files) {
  for (const file of files) {
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!['pdf', 'docx', 'txt', 'md'].includes(ext)) { showErrors([file.name + ': attach a PDF, DOCX, TXT or MD file.']); continue; }
    if (file.size > 50e6) { showErrors([file.name + ' is larger than 50 MB.']); continue; }
    const entry = { name: file.name, busy: true };
    state.form.files.push(entry);
    renderChips();
    try {
      const res = await api('/api/upload?name=' + encodeURIComponent(file.name), { method: 'POST', body: file });
      Object.assign(entry, res, { busy: false });
    } catch (e) {
      state.form.files.splice(state.form.files.indexOf(entry), 1);
      showErrors(e.errors);
    }
    renderChips();
  }
}

function wire() {
  const f = state.form;
  const bind = (id, key, ev) => { const el = $('#' + id); if (el) el.addEventListener(ev || 'input', () => { f[key] = el.type === 'checkbox' ? el.checked : el.value; }); };
  bind('brief', 'topic'); bind('aud', 'audience'); bind('tone', 'tone'); bind('must', 'must'); bind('avoid', 'avoid');
  bind('cta', 'cta'); bind('ctype', 'content_type', 'change'); bind('voice', 'voice', 'change'); bind('lang', 'language', 'change');
  bind('slang', 'subtitle_language', 'change'); bind('ai', 'exec_mode', 'change'); bind('fresh', 'fresh_script', 'change'); bind('seed', 'seed');

  $('#quick').addEventListener('change', (e) => {
    f.quick_test = e.target.checked;
    f.duration = f.quick_test ? 15 : 45;
    $('#len').innerHTML = segmented('Length', lengthChoices(f.quick_test), f.duration);
  });
  $('#adv-btn').addEventListener('click', (e) => {
    f.adv = !f.adv;
    e.currentTarget.setAttribute('aria-expanded', f.adv);
    $('#adv').hidden = !f.adv;
  });
  $('#brief').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); generate(); } });
  $('#go').addEventListener('click', generate);
  $('#file').addEventListener('change', (e) => { uploadFiles(Array.from(e.target.files)); e.target.value = ''; });

  const box = $('#box');
  box.addEventListener('dragover', (e) => { e.preventDefault(); box.classList.add('drag'); });
  box.addEventListener('dragleave', () => box.classList.remove('drag'));
  box.addEventListener('drop', (e) => { e.preventDefault(); box.classList.remove('drag'); uploadFiles(Array.from(e.dataTransfer.files)); });

  wirePreviews();
}

// One delegated listener for the buttons that re-render parts of Create (registered once in main.js).
export function handleCreateClick(e) {
  if (currentRoute().name !== 'create') return;
  const f = state.form;
  const t = e.target.closest('button');
  if (!t) return;
  if (t.id === 'attach') { $('#file').click(); return; }
  if (t.dataset.rm != null) { f.files.splice(Number(t.dataset.rm), 1); renderChips(); return; }
  if (t.dataset.style) {
    f.mode = t.dataset.style;
    selectTile(f.mode);
    $('#motion-field').hidden = f.mode === 'og';
    return;
  }
  if (t.dataset.seg) {
    const key = SEG_FIELD[t.dataset.seg];
    f[key] = key === 'duration' || key === 'speed' ? Number(t.dataset.val) : t.dataset.val;
    $$('button[data-seg="' + t.dataset.seg + '"]').forEach((b) => b.setAttribute('aria-pressed', b === t));
  }
}

async function generate() {
  const f = state.form;
  const btn = $('#go');
  if (btn.disabled) return;
  if (f.files.some((x) => x.busy)) { showErrors(['Wait for the upload to finish.']); return; }
  if ((f.topic || '').trim().length < 3) { showErrors(['Write a few words about what the video should explain.']); $('#brief').focus(); return; }
  btn.disabled = true;
  showErrors(null);
  try {
    const res = await post('/api/jobs', {
      topic: f.topic, mode: f.mode, duration_s: f.duration, format: f.format, content_type: f.content_type,
      voice: f.voice, speed: f.speed, motion: f.motion, audience: f.audience, tone: f.tone, language: f.language,
      subtitle_language: f.subtitle_language || f.language, must_include: f.must, must_avoid: f.avoid, cta: f.cta,
      source_files: f.files.map((x) => x.path), exec_mode: f.exec_mode || undefined, quick_test: f.quick_test,
      seed: Number(f.seed) || 42, fresh_script: f.fresh_script,
    });
    refreshJobs();
    go('/job/' + res.id);
  } catch (e) {
    showErrors(e.errors);
    btn.disabled = false;
  }
}
