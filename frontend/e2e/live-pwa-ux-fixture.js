import { execFile } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const runFile = promisify(execFile);
const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const parent = { id: 91001, username: 'offline_fixture_parent', display_name: 'Synthetic parent', role: 'parent', theme: 'hyrule', family: { id: 91000, name: 'Offline synthetic family' }, is_staff: false };
const child = { id: 91002, username: 'offline_fixture_child', display_name: 'Synthetic child', role: 'child', family: parent.family, hourly_rate: '10.00', is_active: true };

export async function startLivePwaUxFixture() {
  const directory = await mkdtemp(join(tmpdir(), 'live-harness-pwa-fixture-'));
  const output = join(directory, 'bundle');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|HOME|USERPROFILE|SYSTEMROOT|WINDIR|TEMP|TMP)$/i.test(key)));
  try {
    const built = await runFile(process.execPath, [join(frontendRoot, 'e2e/live-pwa-ux-build.mjs'), output], { cwd: frontendRoot, env, maxBuffer: 2 * 1024 * 1024 });
    await writeFile(join(directory, 'build.log'), built.stdout + built.stderr);
  } catch (error) {
    await rm(directory, { recursive: true, force: true });
    throw new Error('Offline PWA production fixture build failed', { cause: error });
  }
  const requests = [];
  const mutations = [];
  const server = createServer(async (request, response) => {
    const path = new URL(request.url, 'http://127.0.0.1').pathname;
    requests.push({ method: request.method, path });
    if (!['GET', 'HEAD'].includes(request.method)) {
      mutations.push({ method: request.method, path });
      response.writeHead(405, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ detail: 'Offline observer fixture refuses every write' }));
      return;
    }
    if (path.startsWith('/api/')) {
      const payloads = { '/api/auth/me/': parent, '/api/children/': [child], '/api/parents/': [parent] };
      const denied = path === '/api/admin/ping/' || path.startsWith('/api/dev-tools/');
      response.writeHead(denied ? 403 : 200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify(denied ? { detail: 'Nonstaff fixture' } : payloads[path] || []));
      return;
    }
    try {
      const asset = path.startsWith('/assets/') ? resolve(output, `.${path}`) : join(output, 'e2e/live-pwa-ux-fixture.html');
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
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolveReady);
  });
  return {
    origin: `http://127.0.0.1:${server.address().port}`, directory, requests, mutations,
    stop: async () => {
      try {
        await new Promise((resolveStopped, reject) => server.close((error) => error ? reject(error) : resolveStopped()));
      } finally {
        await rm(directory, { recursive: true, force: true });
      }
    },
  };
}
