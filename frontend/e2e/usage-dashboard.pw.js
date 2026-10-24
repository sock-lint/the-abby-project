import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers.js';

let server;
let origin;
let familyReport;
let deploymentReport;
let liveParent;
let liveChild;

test.beforeAll(async () => {
  [familyReport, deploymentReport, liveParent, liveChild] = await Promise.all(['usage-family-observed', 'usage-deployment-observed', 'auth-me-live-parent', 'auth-me-live-child'].map(async (name) =>
    JSON.parse(await readFile(new URL(`../../contracts/api/fixtures/${name}.json`, import.meta.url), 'utf8')),
  ));
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Vite startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const url = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (url) { clearTimeout(timer); resolve(url[0]); }
    });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const stopped = once(server, 'exit');
    server.kill();
    await stopped;
  }
});

async function mockApp(page, { denied = false, collectionEnabled = true, identity } = {}) {
  const visits = [];
  const reportReads = [];
  const errors = [];
  const unexpectedWrites = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-usage-browser-session'));
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (url.pathname === '/api/usage/visit/' && request.method() === 'POST') {
      const body = request.postDataJSON();
      visits.push(body);
      expect(url.search).toBe('');
      expect(body).toEqual({});
      if (!collectionEnabled) {
        unexpectedWrites.push({ path: url.pathname, method: request.method() });
        return route.abort();
      }
      return route.fulfill({ status: 204 });
    }
    if (request.method() !== 'GET') {
      unexpectedWrites.push({ path: url.pathname, method: request.method() });
      return route.abort();
    }
    if (url.pathname === '/api/admin/usage/') {
      reportReads.push(Object.fromEntries(url.searchParams));
      if (denied) return route.fulfill({ status: 403, json: { detail: 'Staff parents only.' } });
      const report = structuredClone(url.searchParams.get('scope') === 'deployment' ? deploymentReport : familyReport);
      report.can_view_deployment = true;
      return route.fulfill({ json: report });
    }
    const payloads = {
      '/api/auth/me/': identity ?? { id: 21, username: 'synthetic-staff-parent', role: 'parent', is_staff: true, usage_collection_enabled: collectionEnabled, theme: 'hyrule', family: { id: 81, name: 'Synthetic family' } },
      '/api/pulse/': { unread_count: 0, notifications: [], recent_drops: [], challenge_receipts: [], companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [], header: { active_timer: null, coin_balance: 0, streak_days: 0 } },
      '/api/sprites/catalog/': { sprites: {}, etag: 'synthetic-empty' },
      '/api/push/config/': { enabled: false },
      '/api/admin/families/': { ok: true },
      '/api/dev/ping/': { enabled: false },
      '/api/coins/': { balance: 0, recent: [] },
      '/api/balance/': { balance: 0, breakdown: {}, recent_transactions: [] },
      '/api/clock/': null,
    };
    return route.fulfill({ json: payloads[url.pathname] ?? [] });
  });
  return { visits, reportReads, errors, unexpectedWrites };
}

for (const width of [320, 390, 1280]) {
  test(`staff usage route is readable and keyboard usable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const { visits, reportReads, errors, unexpectedWrites } = await mockApp(page);
    await page.goto(`${origin}/manage/usage`);
    await expect(page.getByRole('heading', { name: 'Usage', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Feature adoption', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Returning families' })).toBeVisible();
    await expect(page.getByText('Synthetic private task title')).toHaveCount(0);
    await expect.poll(() => visits.length).toBe(1);
    expect(visits).toEqual([{}]);
    await chooseDropdown(page.getByRole('combobox', { name: 'Scope', exact: true }), 'deployment');
    await expect.poll(() => reportReads.at(-1)?.scope).toBe('deployment');
    await expect(page.getByText(/^All families ·/)).toBeVisible();
    const refresh = page.getByRole('button', { name: 'Refresh usage' });
    await refresh.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => reportReads.length).toBeGreaterThanOrEqual(3);
    await expect(refresh).toBeEnabled();
    for (const label of ['Scope', 'Date range', 'Role', 'Feature']) {
      const bounds = await page.getByRole('combobox', { name: label, exact: true }).boundingBox();
      expect(bounds.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    expect(unexpectedWrites).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`usage-${width}.png`), fullPage: true });
  });
}

test('a denied report does not display aggregate counts', async ({ page }) => {
  const { errors, unexpectedWrites } = await mockApp(page, { denied: true });
  await page.goto(`${origin}/manage/usage`);
  await expect(page.getByText(/Usage is available to staff parents/)).toBeVisible();
  await expect(page.getByRole('region', { name: 'Feature adoption', exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
  expect(unexpectedWrites).toEqual([]);
});

for (const role of ['parent', 'child']) {
  test(`the excluded observer ${role} identity never attempts foreground visit writes through the full app`, async ({ page }) => {
    const identity = role === 'parent' ? liveParent : liveChild;
    expect(identity.usage_collection_enabled).toBe(false);
    const { visits, errors, unexpectedWrites } = await mockApp(page, { denied: true, collectionEnabled: false, identity });
    await page.goto(`${origin}/manage/usage`);
    await expect(page.getByText(/Usage is available to staff parents/)).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.reload();
    await expect(page.getByText(/Usage is available to staff parents/)).toBeVisible();
    await page.waitForLoadState('networkidle');
    expect(visits).toEqual([]);
    expect(unexpectedWrites).toEqual([]);
    expect(errors).toEqual([]);
  });
}
