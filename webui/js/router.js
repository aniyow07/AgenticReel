// URL routing for the three screens: /create, /job/<id> (rendering, result or failed) and /library.
import { app } from './core/dom.js';
import { clearTimers } from './core/timers.js';
import { renderHeader } from './ui/header.js';
import { viewCreate } from './screens/create.js';
import { viewJob } from './screens/job.js';
import { viewLibrary } from './screens/library.js';

const TITLES = { create: 'Create · AgentReel', library: 'Library · AgentReel' };

export function currentRoute() {
  const p = location.pathname.replace(/\/+$/, '');
  let m;
  if ((m = p.match(/^\/job\/([A-Za-z0-9_\-]+)$/))) return { name: 'job', id: m[1] };
  if (p === '/library') return { name: 'library' };
  return { name: 'create' };
}

export function go(path, replace) {
  if (replace) history.replaceState({}, '', path); else history.pushState({}, '', path);
  route();
}

export function route() {
  clearTimers();
  const r = currentRoute();
  renderHeader(r.name);
  window.scrollTo(0, 0);
  document.title = TITLES[r.name] || 'AgentReel';
  if (r.name === 'job') viewJob(r.id);
  else if (r.name === 'library') viewLibrary();
  else viewCreate();
  app.focus({ preventScroll: true });
}

export function initRouter() {
  // in-app links (data-link) change the URL without reloading the page
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-link]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || a.target === '_blank') return;
    const href = a.getAttribute('href');
    if (!href || href === '#' || href.startsWith('http')) return;
    e.preventDefault();
    go(href);
  });
  window.addEventListener('popstate', route);
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
}
