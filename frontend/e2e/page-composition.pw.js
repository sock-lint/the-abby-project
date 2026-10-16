import { chooseDropdown } from './dropdown-helpers.js';
import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

test.setTimeout(45_000);

let devServer;
let origin;
test.beforeAll(async () => {
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Fixture startup timed out: ${output}`)), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    devServer.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});
test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith('/api/')) return route.continue();
    const parent = new URL(page.url()).searchParams.get('role') === 'parent';
    const payloads = {
      '/api/auth/me/': { id: 2, username: 'fixture', display_name: 'Fixture', role: parent ? 'parent' : 'child', theme: 'hyrule', family: { id: 1, name: 'Synthetic family' } },
      '/api/clock/': { active: null },
      '/api/dashboard/': { next_actions: [{ kind: 'project', id: 3, title: 'Synthetic next task', subtitle: 'A local fixture', icon: 'Play', tone: 'moss', action_url: '/clock' }], active_projects: [], recent_badges: [], savings_goals: [], chores_today: [], this_week: { hours_worked: 0, earnings: 0 }, rpg: { login_streak: 0, longest_login_streak: 0 }, coin_balance: 0 },
      '/api/pulse/': { notifications: [], recent_drops: [], challenge_receipts: [], companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [], header: { active_timer: null, coin_balance: 0, streak_days: 0 } },
      '/api/balance/': { balance: 0, breakdown: {}, recent_transactions: [] },
      '/api/coins/': { balance: 0, recent: [] },
      '/api/coins/exchange/rate/': { coins_per_dollar: 10 },
      '/api/coins/summary-by-day/': { days: 30, series: [] },
      '/api/payments/summary-by-day/': { days: 30, series: [] },
      '/api/portfolio/': { projects: [], homework: [], creations: [] },
      '/api/character/': { level: 1, equipped_items: [], active_boosts: [] },
      '/api/chronicle/summary/': { chapters: [] },
      '/api/auth/google/account/': { linked: false },
      '/api/auth/google/calendar/': { sync_enabled: false },
      '/api/cosmetics/': { active_theme: [] },
      '/api/admin/ping/': { enabled: false },
      '/api/dev/ping/': { enabled: false },
      '/api/push/config/': { enabled: false },
    };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payloads[path] ?? []) });
  });
});

const hubPages = { skills: 'Skills', inventory: 'Inventory', rewards: 'Rewards', portfolio: 'Gallery', yearbook: 'Timeline' };

for (const [width, height, theme] of [[320, 568, 'hyrule'], [390, 844, 'vigil']]) {
  test(`materials can be ready without a purchase at ${width}px on ${theme}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height });
    const writes = [];
    const project = {
      id: 42, title: 'Get ready for a math test', status: 'in_progress',
      difficulty: 2, materials_budget: '5.00', assigned_to: { id: 2 },
      milestones: [], steps: [], resources: [], skill_tags: [], collaborators: [],
      materials: [
        { id: 11, name: 'Class notes and worksheets', estimated_cost: '0.00', actual_cost: null, is_ready: false, is_purchased: false },
        { id: 12, name: 'Notebook or scratch paper', estimated_cost: '3.00', actual_cost: null, is_ready: false, is_purchased: false },
      ],
    };
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path === '/api/auth/me/') {
        return route.fulfill({ json: { id: 2, username: 'material-fixture', display_name: 'Test child', role: 'child', theme, family: { id: 1, name: 'Synthetic family' } } });
      }
      if (path === '/api/projects/42/') return route.fulfill({ json: project });
      if (/^\/api\/projects\/42\/materials\/\d+\/mark-(ready|not-ready|purchased)\/$/.test(path)) {
        const body = request.postDataJSON();
        writes.push({ path, method: request.method(), body });
        const material = project.materials.find((item) => String(item.id) === path.split('/')[5]);
        material.is_ready = path.endsWith('/mark-not-ready/') ? material.is_purchased : true;
        if (path.endsWith('/mark-purchased/')) {
          material.is_purchased = true;
          material.actual_cost = body.actual_cost;
        }
        return route.fulfill({ json: material });
      }
      return route.fallback();
    });
    await page.goto(`${origin}/e2e/page-composition-fixture.html?page=app-materials`);
    await page.getByRole('tab', { name: 'Materials', exact: true }).click();
    await expect(page.getByText('spent $0.00', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const opener = page.getByRole('button', { name: 'Mark ready', exact: true }).first();
    await opener.scrollIntoViewIfNeeded();
    const bounds = await opener.boundingBox();
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: testInfo.outputPath('materials-list.png'), fullPage: true });
    await opener.click();
    const sheet = page.getByRole('dialog', { name: 'Mark material ready', exact: true });
    await expect(sheet.getByLabel('How did you get it?')).toHaveJSProperty('value', 'on_hand');
    await expect(sheet.getByLabel('Actual cost ($)')).toHaveCount(0);
    const save = sheet.getByRole('button', { name: 'Mark ready', exact: true });
    await save.scrollIntoViewIfNeeded();
    expect(await save.evaluate((node) => {
      const box = node.getBoundingClientRect();
      return box.left >= 0 && box.right <= window.innerWidth && box.height >= 44;
    })).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('materials-on-hand.png'), fullPage: true });
    await save.click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByText('Ready', { exact: true })).toHaveCount(1);
    await expect(page.getByText('spent $0.00', { exact: true })).toBeVisible();
    expect(writes).toEqual([{ path: '/api/projects/42/materials/11/mark-ready/', method: 'POST', body: {} }]);
    expect(project.materials[0].is_purchased).toBe(false);
    expect(project.materials[0].actual_cost).toBeNull();

    await page.getByRole('button', { name: 'Change readiness for Class notes and worksheets', exact: true }).click();
    const updateSheet = page.getByRole('dialog', { name: 'Update material readiness', exact: true });
    await chooseDropdown(updateSheet.getByLabel('How did you get it?'), 'needed');
    await updateSheet.getByRole('button', { name: 'Mark not ready', exact: true }).click();
    await expect(updateSheet).toHaveCount(0);
    await expect(page.getByText('Ready', { exact: true })).toHaveCount(0);
    await expect(page.getByText('spent $0.00', { exact: true })).toBeVisible();
    expect(writes[1]).toEqual({ path: '/api/projects/42/materials/11/mark-not-ready/', method: 'POST', body: {} });

    await page.getByRole('button', { name: 'Mark ready', exact: true }).nth(1).click();
    await sheet.getByRole('button', { name: 'Mark ready', exact: true }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByText('Ready', { exact: true })).toHaveCount(1);
    await page.getByRole('button', { name: 'Change readiness for Notebook or scratch paper', exact: true }).click();
    await chooseDropdown(updateSheet.getByLabel('How did you get it?'), 'purchased');
    await updateSheet.getByLabel('Actual cost ($)').fill('1.25');
    await updateSheet.getByRole('button', { name: 'Mark ready', exact: true }).click();
    await expect(updateSheet).toHaveCount(0);
    await expect(page.getByText('Ready', { exact: true })).toHaveCount(1);
    await expect(page.getByText('spent $1.25', { exact: true })).toBeVisible();
    expect(writes[3]).toEqual({ path: '/api/projects/42/materials/12/mark-purchased/', method: 'POST', body: { actual_cost: '1.25' } });
    await page.reload();
    await page.getByRole('tab', { name: 'Materials', exact: true }).click();
    await expect(page.getByText('Ready', { exact: true })).toHaveCount(1);
    await expect(page.getByText('spent $1.25', { exact: true })).toBeVisible();
    expect(writes).toHaveLength(4);
  });
}

test('the real app suppresses clock transforms and Today hero blur under reduced motion', async ({ page }) => {
  await page.goto(`${origin}/e2e/page-composition-fixture.html?page=app-clock`);
  const clock = page.getByRole('button', { name: 'Clock in', exact: true });
  await expect(clock).toBeEnabled();
  await clock.hover();
  await page.mouse.down();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(clock).toHaveCSS('transform', 'none');
  await page.mouse.move(0, 0); await page.mouse.up();
  await page.goto(`${origin}/e2e/page-composition-fixture.html?page=app-today`);
  const hero = page.getByRole('heading', { name: 'Synthetic next task', exact: true }).first();
  await expect(hero).toBeVisible();
  expect(await hero.evaluate((node) => {
    let surface = node;
    while (surface && !surface.classList.contains('rounded-xl')) surface = surface.parentElement;
    return getComputedStyle(surface.parentElement).filter;
  })).toBe('none');
});
for (const [view, title] of Object.entries(hubPages)) {
  test(`${title} keeps an accessible heading without adding a large phone header`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto(`${origin}/e2e/page-composition-fixture.html?page=${view}`);
    const heading = page.getByRole('heading', { name: title, level: 1, exact: true });
    await expect(heading).toBeAttached();
    // Timeline clips its whole opener; other tabs clip only the heading.
    // Measure visible bounds after ancestor clipping in both compositions.
    const phone = await heading.evaluate((node) => {
      let { left, right, top, bottom } = node.getBoundingClientRect();
      for (let parent = node.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        if (style.overflowX !== 'hidden' || style.overflowY !== 'hidden') continue;
        const bounds = parent.getBoundingClientRect();
        left = Math.max(left, bounds.left); right = Math.min(right, bounds.right);
        top = Math.max(top, bounds.top); bottom = Math.min(bottom, bounds.bottom);
      }
      return { width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
    });
    expect(phone.width).toBeLessThanOrEqual(1);
    expect(phone.height).toBeLessThanOrEqual(1);
    await page.setViewportSize({ width: 1280, height: 740 });
    await expect(heading).toBeVisible();
    expect((await heading.boundingBox()).height).toBeGreaterThan(20);
  });
}

for (const [view, title] of Object.entries({ settings: 'Settings', manage: 'Manage', clock: 'Time tracking', payments: 'Payments', timecards: 'Timecards' })) {
  test(`${title} has one readable page heading and contained actions on a phone`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto(`${origin}/e2e/page-composition-fixture.html?page=${view}&role=parent`);
    const heading = page.getByRole('heading', { name: title, level: 1, exact: true });
    await expect(heading).toBeVisible();
    await expect(heading).toHaveCount(1);
    expect((await heading.boundingBox()).x).toBeGreaterThanOrEqual(0);
    expect(await heading.evaluate((node) => node.getBoundingClientRect().right <= window.innerWidth)).toBe(true);
    if (view === 'payments' || view === 'timecards') {
      const actions = [page.getByRole('button', { name: 'Export CSV', exact: true })];
      if (view === 'payments') actions.push(page.getByRole('button', { name: 'Adjust money owed', exact: true }));
      for (const action of actions) {
        const bounds = await action.boundingBox();
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(320);
      }
    }
  });
}

test('Payments filters fit a phone and preserve date selection, reads and clearing', async ({ page }) => {
  const reads = [];
  const mutations = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname === '/api/payments/') reads.push(url);
    if (url.pathname.startsWith('/api/') && request.method() !== 'GET') mutations.push(request.method());
  });
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto(`${origin}/e2e/page-composition-fixture.html?page=payments&role=parent`);
  for (const name of ['This week', 'This month', 'Last 30 days', 'All time', 'Hourly', 'Payout']) {
    const control = page.getByRole('button', { name, exact: true });
    const bounds = await control.boundingBox();
    expect(bounds.height, name).toBeGreaterThanOrEqual(44);
    expect(bounds.x + bounds.width, name).toBeLessThanOrEqual(320);
  }
  await page.getByRole('button', { name: 'This month', exact: true }).click();
  const from = page.getByLabel('From', { exact: true });
  const to = page.getByLabel('To', { exact: true });
  await expect(from).toHaveValue(/\d{4}-\d{2}-01/);
  await expect(to).toHaveValue(/\d{4}-\d{2}-\d{2}/);
  await expect(page.getByRole('button', { name: 'This month', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => reads.length).toBeGreaterThan(0);
  expect(reads.at(-1).searchParams.get('start_date')).toBe(await from.inputValue());
  expect(reads.at(-1).searchParams.get('end_date')).toBe(await to.inputValue());
  const clear = page.getByRole('button', { name: 'Clear all filters', exact: true });
  expect((await clear.boundingBox()).height).toBeGreaterThanOrEqual(44);
  await clear.click();
  await expect(from).toHaveValue('');
  await expect(to).toHaveValue('');
  await expect(clear).not.toBeAttached();
  expect(mutations).toEqual([]);
});
