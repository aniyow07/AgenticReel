// The step pills on the Rendering screen, tagged with where each writing step came from.
import { esc } from '../core/dom.js';
import { icon } from '../core/icons.js';

const SOURCE_LABEL = { ai: 'AI', reused: 'reused', template: 'template' };

export function progressSteps(p) {
  return p.steps.map((s) => {
    const cls = s.status === 'done' || s.status === 'skipped' ? 'done' : (s.current ? 'cur' : (s.status === 'failed' ? 'failed' : ''));
    const src = SOURCE_LABEL[s.source];
    return '<li class="' + cls + '">' + (cls === 'done' ? icon.check : '') + esc(s.name) + (s.current && s.attempts > 1 ? ' · try ' + s.attempts : '') +
      (src ? '<span class="src src-' + s.source + '">' + src + '</span>' : '') + '</li>';
  }).join('');
}

export function aiSkippedNotice(p) {
  return p.ai_skipped ? '<p class="notice warn">The AI was skipped for some steps because ' + esc(p.ai_skipped) +
    '. Steps marked template used built-in text instead.</p>' : '';
}
