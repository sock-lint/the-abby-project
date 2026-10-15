import { execFile } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const runFile = promisify(execFile);
const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const child = {
  id: 7, username: 'offline_tasks_child', display_name: 'Synthetic child',
  role: 'child', theme: 'hyrule', hourly_rate: '10.00', is_staff: false,
  family: { id: 70, name: 'Synthetic Tasks family', timezone: 'UTC' },
};
const chore = {
  id: 71, title: 'Synthetic dishes', description: 'Loopback fixture chore',
  icon: '🧹', reward_amount: '1.00', coin_reward: 2, xp_reward: 10,
  recurrence: 'daily', week_schedule: 'every_week', is_active: true,
  is_available: true, is_active_this_week: true, today_status: null,
};
const habit = {
  id: 72, name: 'Synthetic reading', icon: '📖', habit_type: 'positive',
  user: child.id, strength: 0, xp_reward: 5, max_taps_per_day: 1,
  taps_today: 0, is_active: true,
};

export async function startLiveChildTasksFixture() {
  const directory = await mkdtemp(join(tmpdir(), 'live-harness-child-tasks-'));
  const output = join(directory, 'bundle');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|HOME|USERPROFILE|SYSTEMROOT|WINDIR|TEMP|TMP)$/i.test(key)));
  try {
    const built = await runFile(process.execPath, [join(frontendRoot, 'e2e/live-child-tasks-build.mjs'), output], { cwd: frontendRoot, env, maxBuffer: 2 * 1024 * 1024 });
    await writeFile(join(directory, 'build.log'), built.stdout + built.stderr);
  } catch (error) {
    await rm(directory, { recursive: true, force: true });
    throw new Error('Offline child Tasks fixture build failed', { cause: error });
  }
  const requests = [];
  const mutations = [];
  let populated = false;
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    const path = url.pathname;
    requests.push({ method: request.method, path, pending: url.searchParams.get('pending') });
    if (!['GET', 'HEAD'].includes(request.method)) {
      mutations.push({ method: request.method, path });
      response.writeHead(405, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ detail: 'Offline Tasks fixture refuses every write' }));
      return;
    }
    if (path.startsWith('/api/')) {
      let payload = [];
      if (path === '/api/auth/me/') payload = child;
      else if (path === '/api/portfolio/') payload = { projects: [], homework: [], creations: [] };
      else if (path === '/api/habits/history/') payload = { histories: {} };
      else if (url.searchParams.get('pending') !== 'true' && populated) {
        if (path === '/api/chores/') payload = [chore];
        if (path === '/api/habits/') payload = [habit];
      }
      response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify(payload));
      return;
    }
    try {
      const asset = path.startsWith('/assets/') ? resolve(output, `.${path}`) : join(output, 'e2e/live-child-tasks-fixture.html');
      if (!asset.startsWith(output + '/')) throw new Error('Fixture asset escapes its bundle');
      const content = await readFile(asset);
      const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png' };
      response.writeHead(200, { 'Content-Type': types[extname(asset)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      response.end(content);
    } catch {
      response.writeHead(404); response.end();
    }
  });
  await new Promise((resolveReady, reject) => {
    server.once('error', reject); server.listen(0, '127.0.0.1', resolveReady);
  });
  return {
    origin: `http://127.0.0.1:${server.address().port}`, directory, requests, mutations,
    setPopulated: (value) => { populated = value; requests.length = 0; mutations.length = 0; },
    stop: async () => {
      try {
        await new Promise((resolveStopped, reject) => server.close((error) => error ? reject(error) : resolveStopped()));
      } finally {
        await rm(directory, { recursive: true, force: true });
      }
    },
  };
}
