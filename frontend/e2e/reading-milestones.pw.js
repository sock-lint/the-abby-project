import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { buildParent, buildUser } from '../src/test/factories.js';
import { chooseDropdown } from './dropdown-helpers.js';

const fixture = (name) => JSON.parse(readFileSync(new URL(`../../contracts/api/fixtures/${name}`, import.meta.url), 'utf8'));
const locked = fixture('challenges-milestone-locked.json');
const ready = fixture('challenges-milestone-ready.json');
const workbench = fixture('content-workbench-catalog.json');
let devServer;
let origin;
test.use({ actionTimeout: 15_000 });
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

async function prepare(page, width, height, auth) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-milestone-browser-session'));
  const unexpected = [];
  const calls = [];
  return {
    errors, unexpected, calls,
    route: async (handler) => page.route('**/*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== origin) {
        unexpected.push(`${request.method()} ${url.origin}${url.pathname}`);
        return route.abort();
      }
      if (!url.pathname.startsWith('/api/')) return route.continue();
      const record = { method: request.method(), path: url.pathname };
      calls.push(record);
      if ([...url.searchParams.keys()].some((key) => !['_abby_session', '_abby_retry'].includes(key))) unexpected.push(`query ${url.search}`);
      if (record.method === 'GET' && record.path === '/api/auth/me/') return route.fulfill({ json: auth });
      if (await handler(route, record)) return;
      unexpected.push(`${record.method} ${record.path}`);
      return route.fulfill({ status: 500, json: { detail: 'Unexpected synthetic request.' } });
    }),
  };
}

async function noPageOverflow(page) {
  const size = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }));
  expect(size.page).toBeLessThanOrEqual(size.viewport);
}

for (const [state, body, width, height] of [['locked', locked, 375, 812], ['ready', ready, 375, 812], ['locked', locked, 1280, 900], ['ready', ready, 1280, 900]]) {
  test(`${state} milestone preview stays read-only at ${width}px using the actual challenge response`, async ({ page }) => {
    const observed = await prepare(page, width, height, buildUser());
    await observed.route(async (route, request) => {
      if (request.method === 'GET' && request.path === '/api/challenges/') {
        await route.fulfill({ json: body });
        return true;
      }
      return false;
    });
    await page.goto(`${origin}/e2e/reading-milestones-fixture.html`);
    const definition = body.locked_catalog.find((row) => row.name === 'Reading Voyager');
    expect(definition.duration_days).toBe(56);
    const coming = page.getByRole('region', { name: 'Coming next', exact: true });
    await expect(coming.getByText(state === 'ready' ? 'Requirements met' : 'Locked challenge', { exact: true })).toBeVisible();
    if (state === 'ready') await expect(coming.getByText('Your next matching saved activity can start this challenge.')).toBeVisible();
    const opener = coming.getByRole('button', { name: 'View requirements for Reading Voyager', exact: true });
    await opener.click();
    const dialog = page.getByRole('dialog', { name: 'Reading Voyager requirements', exact: true });
    for (const requirement of definition.milestone_eligibility.requirements) {
      const row = dialog.getByRole('list', { name: 'Reading Voyager milestone requirements' }).getByRole('listitem').filter({ hasText: requirement.description });
      await expect(row).toContainText(requirement.met ? 'Met' : 'Not yet met');
    }
    await expect(dialog.getByText(/No deadline is running yet.*56 days after it starts/)).toBeVisible();
    await expect(dialog.getByRole('progressbar')).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: /Pin|Start|Begin|Log reading/i })).toHaveCount(0);
    await noPageOverflow(page);
    await page.screenshot({ path: `/tmp/reading-milestones-${state}-${width}.png`, fullPage: true });
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    expect(observed.calls.every((call) => call.method === 'GET')).toBe(true);
    expect(observed.unexpected).toEqual([]);
    expect(observed.errors).toEqual([]);
  });
}

for (const width of [375, 1280]) {
  test(`milestone draft editor retains real catalog IDs without publishing at ${width}px`, async ({ page }) => {
    const observed = await prepare(page, width, 900, buildParent());
    // Draft responses are synthetic; the catalog is the unchanged actual producer fixture.
    const draftId = 'd0000000-0000-4000-8000-000000000056';
    let draft = { id: draftId, name: 'Milestone review', revision: 1, changes: [], published_at: null, preview: null };
    const mutations = [];
    await observed.route(async (route, request) => {
      if (request.method === 'GET' && request.path === '/api/rpg/content-workbench/') {
        await route.fulfill({ json: workbench });
        return true;
      }
      if (request.method === 'POST' && request.path === '/api/rpg/content-workbench/drafts/') {
        const body = route.request().postDataJSON();
        mutations.push({ ...request, body });
        expect(body).toEqual({ name: draft.name });
        await route.fulfill({ json: draft, status: 201 });
        return true;
      }
      if (request.method === 'PATCH' && request.path === `/api/rpg/content-workbench/drafts/${draftId}/`) {
        const body = route.request().postDataJSON();
        mutations.push({ ...request, body });
        draft = { ...draft, revision: 2, changes: body.changes };
        await route.fulfill({ json: draft });
        return true;
      }
      return false;
    });
    await page.goto(`${origin}/e2e/content-workbench-fixture.html`);
    await page.getByRole('textbox', { name: 'New draft name' }).fill(draft.name);
    await page.getByRole('button', { name: 'Create draft', exact: true }).click();
    await page.getByRole('button', { name: /⚔️ Practice challenge/ }).click();
    const editor = page.getByRole('form', { name: 'Challenge editor' });
    await expect(editor.getByRole('combobox', { name: 'Previous challenge', exact: true })).toContainText('Starter practice');
    await expect(editor.getByRole('combobox', { name: 'Required skill', exact: true })).toContainText('Persistence');
    await expect(editor.getByRole('spinbutton', { name: 'Required skill level' })).toHaveValue('1');
    await chooseDropdown(editor.getByRole('combobox', { name: 'Previous challenge', exact: true }), { label: 'No previous challenge required' });
    await chooseDropdown(editor.getByRole('combobox', { name: 'Previous challenge', exact: true }), { label: 'Starter practice' });
    await chooseDropdown(editor.getByRole('combobox', { name: 'Required skill', exact: true }), { label: 'No skill required' });
    await expect(editor.getByRole('spinbutton', { name: 'Required skill level' })).toHaveValue('0');
    await chooseDropdown(editor.getByRole('combobox', { name: 'Required skill', exact: true }), { label: 'Life Skills / Persistence' });
    await editor.getByRole('spinbutton', { name: 'Duration in days' }).fill('56');
    await editor.getByRole('button', { name: 'Save to draft', exact: true }).click();
    await expect(page.getByText(/Changes saved to draft/)).toBeVisible();
    const target = workbench.catalog.quests.find((row) => row.id === 904);
    expect(mutations).toEqual([
      { method: 'POST', path: '/api/rpg/content-workbench/drafts/', body: { name: 'Milestone review' } },
      { method: 'PATCH', path: `/api/rpg/content-workbench/drafts/${draftId}/`, body: {
        revision: 1,
        changes: [{ section: 'quests', object_id: 904, key: 'quests-904', values: { ...target.values, duration_days: 56 } }],
      } },
    ]);
    await expect(page.getByRole('button', { name: 'Publish reviewed draft', exact: true })).toHaveCount(0);
    await noPageOverflow(page);
    await page.screenshot({ path: `/tmp/reading-milestones-workbench-${width}.png`, fullPage: true });
    expect(observed.unexpected).toEqual([]);
    expect(observed.errors).toEqual([]);
  });
}
