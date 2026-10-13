import { readdir, readFile } from 'node:fs/promises';

// Playwright launches Chromium in another process group. Track descendants
// before termination so both the CLI group and browser groups are drained.
async function processes() {
  const names = (await readdir('/proc')).filter((name) => /^\d+$/.test(name));
  const rows = await Promise.all(names.map(async (name) => {
    try {
      const stat = await readFile(`/proc/${name}/stat`, 'utf8');
      const fields = stat.slice(stat.lastIndexOf(')') + 1).trim().split(/\s+/);
      return { pid: Number(name), state: fields[0], parent: Number(fields[1]),
        group: Number(fields[2]), started: fields[19] };
    } catch { return null; }
  }));
  return rows.filter(Boolean);
}

function signal(pid, value) {
  try { process.kill(pid, value); } catch { /* Exit races are expected. */ }
}

export class LiveProcessGroup {
  constructor(child) {
    this.child = child;
    this.known = new Map();
    this.group = null;
    this.failed = false;
  }

  async start() {
    await this.track();
    if (!this.stopping) {
      this.timer = setInterval(() => {
        void this.track().catch(() => { this.failed = true; });
      }, 250);
    }
  }

  async track() {
    const snapshot = await processes();
    this.group ??= snapshot.find((row) => row.pid === process.pid)?.group;
    if (this.known.size === 0) {
      const initial = snapshot.find((row) => row.pid === this.child.pid);
      if (initial) this.known.set(initial.pid, initial.started);
    }
    const live = snapshot.filter((row) => this.known.get(row.pid) === row.started && row.state !== 'Z');
    const ids = new Set(live.map((row) => row.pid));
    const groups = new Set(live.map((row) => row.group).filter((group) => group !== this.group));
    let changed;
    do {
      changed = false;
      for (const row of snapshot) {
        if (row.state !== 'Z' && !ids.has(row.pid) && (ids.has(row.parent) || groups.has(row.group))) {
          ids.add(row.pid);
          if (row.group !== this.group) groups.add(row.group);
          this.known.set(row.pid, row.started);
          changed = true;
        }
      }
    } while (changed);
    return snapshot.filter((row) => ids.has(row.pid) && row.state !== 'Z');
  }

  stop() {
    this.stopping ??= this.drain();
    return this.stopping;
  }

  async drain() {
    clearInterval(this.timer);
    try {
      let live = await this.track();
      const grace = Date.now() + 2_000;
      for (const row of live) signal(row.pid, 'SIGTERM');
      for (const group of new Set(live.map((row) => row.group))) {
        if (group !== this.group) signal(-group, 'SIGTERM');
      }
      while (live.length > 0 && Date.now() < grace) {
        await new Promise((done) => setTimeout(done, 50));
        live = await this.track();
      }
      const deadline = Date.now() + 2_000;
      while (live.length > 0 && Date.now() < deadline) {
        for (const row of live) signal(row.pid, 'SIGKILL');
        for (const group of new Set(live.map((row) => row.group))) {
          if (group !== this.group) signal(-group, 'SIGKILL');
        }
        await new Promise((done) => setTimeout(done, 50));
        live = await this.track();
      }
      return live.length === 0 && !this.failed;
    } catch { return false; }
  }
}
