// /job/<id>: loads the video and shows the screen for its state (rendering, result, or failed/stopped).
import { app, esc } from '../core/dom.js';
import { api } from '../core/api.js';
import { title } from '../core/format.js';
import { renderRendering } from './rendering.js';
import { renderResult } from './result.js';
import { renderFailed } from './failed.js';

const SKELETON = '<div class="page" aria-busy="true"><div class="sk" style="height:40px;width:60%"></div><div class="sk" style="height:16px;width:40%"></div>' +
  '<div class="split"><div class="sk" style="flex:0 0 340px;aspect-ratio:9/16;border-radius:16px"></div><div class="sk" style="flex:1 1 280px;height:52px;border-radius:12px"></div></div></div>';

export function showJob(d) {
  if (d.status === 'running') renderRendering(d);
  else if (d.has_video) renderResult(d);
  else renderFailed(d);
}

export async function viewJob(id) {
  app.innerHTML = SKELETON;
  let d;
  try { d = await api('/api/jobs/' + id); } catch (e) {
    app.innerHTML = '<div class="page"><h1>Video not found</h1><p class="lead">' + esc((e.errors || [])[0]) + '</p><div><a class="btn" href="/library" data-link>Open the library</a></div></div>';
    return;
  }
  document.title = title(d.title) + ' · AgentReel';
  showJob(d);
}
