import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import path from 'node:path';

const fixture = async (name) => JSON.parse(await readFile(new URL(`../../contracts/api/fixtures/egg-discovery-${name}.json`, import.meta.url), 'utf8'));
const catalog = await fixture('catalog');
const missed = await fixture('rare-missed');
const guaranteed = await fixture('rare-guaranteed');
const seasonal = await fixture('season-retained');
const disabled = await fixture('disabled');
const clone = (value) => structuredClone(value);
const browserName = process.env.ABBY_EGG_DISCOVERY_BROWSER === 'webkit' ? 'webkit' : 'chromium';
let server;
let origin;

test.use({ browserName, actionTimeout: 15_000, reducedMotion: 'reduce' });
test.setTimeout(90_000);
test.beforeAll(async () => {
  server = spawn(process.execPath, ['--input-type=module', '-e', "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: 0, hmr: false, watch: null } }); await server.listen(); server.printUrls();"], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Egg discovery fixture startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Egg discovery fixture exited ${code}: ${output}`)); });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

async function open(page, { mode = 'rare', family = false, query = '' } = {}) {
  const errors = [], external = [], unexpected = [], writes = [], reads = [];
  let envelope = mode === 'disabled' ? clone(disabled) : mode === 'seasonal' ? clone(seasonal) : clone(catalog);
  const rareOffer = clone(missed.offers.find((row) => row.tier === 'rare'));
  const rareName = rareOffer.name;
  if (mode === 'rare') {
    envelope.offers = [{ ...rareOffer, eligible: true, unavailable_reason: null }];
    envelope.discoveries = [];
    envelope.active_id = null;
  } else if (mode === 'seasonal') {
    envelope.active_id = null;
    envelope.discoveries[0].status = 'paused';
    envelope.discoveries[0].can_resume = true;
  }
  let practiceCount = 0;
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-browser-egg-token'));
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
    const send = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (url.pathname === '/api/auth/me/') return send({ id: 7, username: 'synthetic-kid', role: family ? 'parent' : 'child', is_staff: false, family: { id: 9, timezone: 'America/Phoenix' } });
    if (url.pathname === '/api/egg-discoveries/' && request.method() === 'GET') { reads.push(url.pathname); return send(envelope); }
    if (request.method() === 'POST') {
      const body = request.postDataJSON();
      writes.push({ path: url.pathname, body });
      expect(request.headers().authorization).toBe('Token synthetic-browser-egg-token');
      if (url.pathname === '/api/egg-discoveries/select/') {
        if (mode === 'seasonal') {
          envelope.discoveries[0].status = 'active';
          envelope.discoveries[0].can_resume = false;
        } else {
          envelope.discoveries = [{ ...clone(missed.discoveries[0]), minutes: { reading: 0, movement: 0, practice: 0 }, searches: [], remaining_searches: 5 }];
        }
        envelope.active_id = envelope.discoveries[0].id;
        return send(envelope, 201);
      }
      if (url.pathname === '/api/reading-sessions/') {
        envelope.discoveries[0].minutes.reading += body.duration_minutes;
        return send({ id: 100 + writes.length, ...body }, 201);
      }
      if (url.pathname === '/api/egg-discoveries/practice/') {
        practiceCount += 1;
        if (practiceCount === 5) envelope = clone(guaranteed);
        else {
          const discovery = envelope.discoveries[0];
          discovery.minutes.practice += body.minutes;
          discovery.searches = Array.from({ length: practiceCount }, (_, index) => ({ number: index + 1, found: false, guaranteed: false }));
          discovery.remaining_searches = 5 - practiceCount;
        }
        return send(envelope, 201);
      }
      unexpected.push(`${request.method()} ${url.pathname}`);
      return send({}, 404);
    }
    if (url.pathname.startsWith('/api/')) { unexpected.push(`${request.method()} ${url.pathname}`); return send({}, 404); }
    return route.continue();
  });
  const loaded = page.waitForResponse((response) => new URL(response.url()).pathname === (family ? '/api/auth/me/' : '/api/egg-discoveries/'), { timeout: 45_000 });
  await Promise.all([loaded, page.goto(`${origin}/e2e/egg-discovery-fixture.html?account=${family ? 'family' : 'child'}${query}`, { waitUntil: 'domcontentloaded' })]);
  await expect(page.getByRole('heading', { name: 'Synthetic egg discovery review' })).toBeVisible();
  return { errors, external, unexpected, writes, reads, rareName };
}

async function capture(page, info, name) {
  const root = process.env.ABBY_EGG_DISCOVERY_CAPTURE_DIR;
  const destination = root ? path.join(root, name) : info.outputPath(name);
  await mkdir(path.dirname(destination), { recursive: true });
  await page.screenshot({ path: destination, fullPage: true });
  info.annotations.push({ type: 'capture', description: destination });
}

async function fits(page) {
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const geometry = await page.locator('button:visible, a:visible').evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return { name: node.textContent, left: rect.left, right: rect.right, height: rect.height };
  }));
  for (const control of geometry) {
    expect(control.left, control.name).toBeGreaterThanOrEqual(-1);
    expect(control.right, control.name).toBeLessThanOrEqual(page.viewportSize().width + 1);
    expect(control.height, control.name).toBeGreaterThanOrEqual(44);
  }
}

function safe(state) {
  expect(state.errors).toEqual([]);
  expect(state.external).toEqual([]);
  expect(state.unexpected).toEqual([]);
}

  test.describe(browserName, () => {
    for (const viewport of [{ width: 320, height: 640 }, { width: 390, height: 844 }, { width: 1280, height: 900 }]) {
      test(`chosen rare egg, activity, saved miss, and guaranteed receipt fit ${viewport.width}px`, async ({ page }, info) => {
        await page.setViewportSize(viewport);
        const state = await open(page);
        const choose = page.getByRole('button', { name: `Choose ${state.rareName}` });
        await choose.focus(); await choose.press('Enter');
        const active = page.getByRole('region', { name: 'Your active egg discovery' });
        await expect(active).toContainText('0 of 5 searches completed');
        await expect(page.getByText('Choose another egg', { exact: true })).toBeVisible();
        await expect(page.getByRole('region', { name: 'Available egg discoveries' }).locator('details')).not.toHaveAttribute('open');
        await fits(page);
        await capture(page, info, `egg-discovery-${browserName}-${viewport.width}-chosen.png`);
        for (let search = 1; search <= 5; search += 1) {
          await page.getByRole('link', { name: 'Log reading', exact: true }).click();
          const reading = page.getByRole('dialog', { name: 'Log your reading' });
          await reading.getByRole('spinbutton', { name: 'Minutes (optional)', exact: true }).fill('30');
          await reading.getByRole('button', { name: 'Save reading', exact: true }).click();
          await expect(active).toBeVisible();
          await page.getByRole('button', { name: 'Log making or practice', exact: true }).click();
          const practice = page.getByRole('dialog', { name: 'Log making or practice' });
          await practice.getByRole('textbox', { name: 'What did you make or practice?' }).fill('Drawing');
          await practice.getByRole('spinbutton', { name: 'Minutes', exact: true }).fill('30');
          await fits(page);
          await practice.getByRole('button', { name: 'Save activity', exact: true }).click();
          if (search < 5) {
            await expect(active).toContainText(`${search} of 5 searches completed`);
            await expect(active.getByRole('list', { name: 'Saved search results' })).toContainText(`Search ${search}: No egg found`);
            if (search === 1) {
              await page.reload();
              await expect(active).toContainText('1 of 5 searches completed');
              await capture(page, info, `egg-discovery-${browserName}-${viewport.width}-saved-miss.png`);
            }
          }
        }
        const earned = page.getByRole('region', { name: `Earned ${state.rareName}` });
        await expect(earned).toContainText('Search 5: Egg found — guaranteed discovery');
        await expect(earned.getByRole('list', { name: 'Discovery supplies' })).toContainText('Discovery Rare Egg × 1');
        await fits(page);
        await capture(page, info, `egg-discovery-${browserName}-${viewport.width}-guaranteed.png`);
        await earned.getByRole('link', { name: 'Take your egg to the Hatchery' }).click();
        await expect(page.getByRole('heading', { name: 'Hatchery destination' })).toBeVisible();
        await expect(page.getByLabel('Fixture location')).toHaveText('/bestiary?tab=hatchery');
        expect(state.writes.filter((row) => row.path.endsWith('/select/'))).toHaveLength(1);
        expect(state.writes.filter((row) => row.path.endsWith('/practice/'))).toHaveLength(5);
        expect(new Set(state.writes.map((row) => row.body.client_request_id)).size).toBe(11);
        safe(state);
      });
    }

    test('seasonal accepted work resumes after its window at 320px and 150% text', async ({ page }, info) => {
      await page.setViewportSize({ width: 320, height: 640 });
      await page.clock.setFixedTime(new Date('2026-11-05T12:00:00Z'));
      const state = await open(page, { mode: 'seasonal', query: '&text=150&theme=vigil' });
      const discovery = seasonal.discoveries[0];
      await expect(page.getByText('Seasonal discovery saved. You can finish after the season ends.')).toBeVisible();
      await page.getByRole('button', { name: `Resume ${discovery.name}` }).click();
      const active = page.getByRole('region', { name: 'Your active egg discovery' });
      await expect(active).toContainText('45 of 240 minutes recorded');
      await fits(page);
      await capture(page, info, `egg-discovery-${browserName}-seasonal-150.png`);
      expect(state.writes).toHaveLength(1);
      safe(state);
    });

    test('disabled and parent Family views hide discovery controls without writes', async ({ page }) => {
      const disabledState = await open(page, { mode: 'disabled' });
      await expect(page.getByRole('heading', { name: 'Egg discoveries', exact: true })).toHaveCount(0);
      await expect(page.getByRole('button')).toHaveCount(0);
      expect(disabledState.writes).toEqual([]);
      expect(disabledState.reads).toHaveLength(1);
      safe(disabledState);
      await page.unroute('**/*');
      const familyState = await open(page, { family: true });
      await expect(page.getByRole('heading', { name: 'Egg discoveries', exact: true })).toHaveCount(0);
      await expect(page.getByRole('button')).toHaveCount(0);
      expect(familyState.writes).toEqual([]);
      expect(familyState.reads).toEqual([]);
      safe(familyState);
    });
  });
