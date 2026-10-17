// The three style cards. Full size on Create (with a preview clip on hover), short on the result page.
import { $, $$, esc } from '../core/dom.js';
import { STYLES } from '../config.js';
import { state } from '../state.js';

export function styleTiles(selected, short) {
  return '<div class="tiles' + (short ? ' short' : '') + '">' + Object.keys(STYLES).map((k) => {
    const st = STYLES[k];
    const ready = !state.info || state.info.ready[k] !== false;
    return '<button type="button" class="tile" data-style="' + k + '" aria-pressed="' + (k === selected) + '"' + (ready ? '' : ' disabled') + '>' +
      // gameplay stills are not in the repository; a fresh clone shows a plain card until the clips are set up
      '<span class="pic"><img src="/static/img/style_' + k + '.jpg" alt="" onerror="this.remove()">' +
      (short ? '' : '<video muted loop playsinline preload="none" src="/ui/preview_' + k + '.mp4"></video>') + '</span>' +
      '<span><span class="name">' + esc(st.name) + '</span>' +
      (short ? '' : '<br><span class="desc">' + esc(st.desc) + '</span>') +
      (ready ? '' : '<br><span class="warn">No footage set up</span>') + '</span></button>';
  }).join('') + '</div>';
}

export function selectTile(mode) {
  $$('.tile').forEach((x) => x.setAttribute('aria-pressed', x.dataset.style === mode));
}

// Play each card's example clip while the pointer is over it.
export function wirePreviews() {
  $$('.tile').forEach((t) => {
    const v = $('video', t);
    if (!v) return;
    t.addEventListener('mouseenter', () => { v.preload = 'auto'; v.play().then(() => v.classList.add('ready')).catch(() => {}); });
    t.addEventListener('mouseleave', () => { v.pause(); });
  });
}
