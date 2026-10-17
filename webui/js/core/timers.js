// Polling timers that belong to the current screen; the router clears them on every navigation.

let timers = [];

export function every(ms, fn) { const t = setInterval(fn, ms); timers.push(t); return t; }
export function clearTimers() { timers.forEach(clearInterval); timers = []; }
