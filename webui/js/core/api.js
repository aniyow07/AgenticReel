// Calls to the local server. Failed requests throw an Error whose .errors holds readable messages.

export async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const err = new Error('request failed');
    err.errors = (data && data.errors) || ['Something went wrong (' + res.status + ').'];
    throw err;
  }
  return data;
}

export const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
