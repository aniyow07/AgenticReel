// The animated 9:16 preview on the Rendering screen. It shows this video's own plan as it appears:
// "Planning" first, then the script lines once they are written, then a card per storyboard scene.
import { $, esc } from '../core/dom.js';
import { every } from '../core/timers.js';

const SCENE_MS = 2800;

function stage(d) {
  if (d.scenes && d.scenes.length) return 'scenes';
  if (d.script && d.script.length) return 'script';
  return 'planning';
}

function sceneCard(s, i, n) {
  return '<div class="lp-top"><span>Scene ' + (i + 1) + ' of ' + n + '</span><span>' + esc(s.kind) + '</span></div>' +
    '<div class="lp-card">' +
      '<p class="lp-text">' + esc(s.text || s.kind) + '</p>' +
      (s.items.length ? '<ol class="lp-items">' + s.items.map((x, k) => '<li style="--i:' + k + '">' + esc(x) + '</li>').join('') + '</ol>' : '') +
    '</div>' +
    '<div class="lp-dots" aria-hidden="true">' + Array.from({ length: n }, (_, k) => '<span' + (k === i ? ' class="on"' : '') + '></span>').join('') + '</div>';
}

function scriptView(lines, i) {
  const start = Math.max(0, i - 2);
  return '<div class="lp-top"><span>Script</span><span>' + lines.length + ' lines</span></div>' +
    '<ol class="lp-lines">' + lines.slice(start, i + 1).map((l, k) =>
      '<li class="' + (start + k === i ? 'now' : '') + '">' + esc(l) + '</li>').join('') + '</ol>';
}

const planningView = '<div class="lp-top"><span>Planning</span><span></span></div>' +
  '<div class="lp-plan"><span></span><span></span><span></span><p>Working out the scenes</p></div>';

export function livePreview(d) {
  return '<div class="frame live mode-' + esc(d.mode) + '" id="lp" aria-hidden="true"><div class="lp-bg"></div><div class="lp-body" id="lp-body"></div></div>';
}

// Starts the slideshow; returns update(detail) for the Rendering screen's poll.
export function startLivePreview(d) {
  let data = d, i = 0, shown = '';
  const draw = () => {
    const body = $('#lp-body');
    if (!body) return;
    const st = stage(data);
    let html;
    if (st === 'scenes') html = sceneCard(data.scenes[i % data.scenes.length], i % data.scenes.length, data.scenes.length);
    else if (st === 'script') html = scriptView(data.script, i % data.script.length);
    else html = planningView;
    if (html !== shown) { body.innerHTML = html; shown = html; }
  };
  draw();
  every(SCENE_MS, () => { i += 1; draw(); });
  return (n) => {
    const grew = stage(n) !== stage(data);
    data = n;
    if (grew) i = 0;
    draw();
  };
}
