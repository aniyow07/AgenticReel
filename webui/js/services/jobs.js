// The job list, version grouping, and deleting with undo.
import { api, post } from '../core/api.js';
import { title } from '../core/format.js';
import { state } from '../state.js';
import { confirmBox } from '../ui/dialog.js';
import { renderHeader } from '../ui/header.js';
import { toast } from '../ui/toast.js';
import { currentRoute, route } from '../router.js';

export async function refreshJobs() {
  try { state.jobs = await api('/api/jobs'); } catch (e) { /* server busy; keep the last list */ }
  renderHeader(currentRoute().name);
  return state.jobs;
}

// One tile per group of versions (newest first); a running version takes the tile so its progress shows.
export function groupHeads(jobs) {
  const seen = new Map();
  jobs.forEach((j) => {
    if (!seen.has(j.group) || (j.status === 'running' && seen.get(j.group).status !== 'running')) seen.set(j.group, j);
  });
  return Array.from(seen.values());
}

export const versionsOf = (job) => state.jobs.filter((j) => j.group === job.group);

// Ask first, move to the trash, then offer Undo. Returns the deleted ids, or null.
export async function deleteJob(job, allVersions) {
  const n = allVersions ? job.versions : 1;
  const ok = await confirmBox(
    n > 1 ? 'Delete this video and its ' + (n - 1) + (n === 2 ? ' other version?' : ' other versions?') : 'Delete this video?',
    '"' + title(job.title) + '" moves to the trash folder inside outputs. You can undo right after.',
    n > 1 ? 'Delete ' + n + ' videos' : 'Delete');
  if (!ok) return null;
  toast('Deleting…');
  try {
    const res = await post('/api/jobs/' + job.id + '/delete', { all_versions: allVersions });
    await refreshJobs();
    toast(res.deleted.length > 1 ? res.deleted.length + ' videos deleted' : 'Video deleted', 'Undo', async () => {
      try {
        await post('/api/restore', { ids: res.deleted });
        await refreshJobs();
        toast(res.deleted.length > 1 ? 'Videos restored' : 'Video restored');
        route();
      } catch (e) { toast((e.errors || ['Could not restore.'])[0]); }
    });
    return res.deleted;
  } catch (e) {
    toast((e.errors || ['Could not delete.'])[0]);
    return null;
  }
}
