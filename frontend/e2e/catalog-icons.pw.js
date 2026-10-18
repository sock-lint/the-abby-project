import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { access, mkdir } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers.js';

// Purchased images must never enter default Playwright traces or reports.
// Evidence screenshots below require an explicit private output directory.
test.use({ trace: 'off', video: 'off', screenshot: 'off' });

// Artwork remains an ignored private import. Hosted code-only runs explicitly
// skip these checks; local acceptance requires the locked family to be installed.
const frontend = fileURLToPath(new URL('..', import.meta.url));
let privateImport = true;
try { await access(`${frontend}/src/avatar/shared/abby-catalog-icons`); } catch { privateImport = false; }
test.skip(!privateImport, 'The private catalog family must be imported for browser artwork acceptance.');

let devServer;
let origin;
const evidence = process.env.ABBY_CATALOG_EVIDENCE_DIR;
const syntheticSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><circle cx="128" cy="128" r="100" fill="#74a68c"/><path d="m80 128 32 32 64-64" fill="none" stroke="white" stroke-width="16"/></svg>';

test.beforeAll(async () => {
  devServer = spawn(process.execPath, [
    `${frontend}/node_modules/vite/bin/vite.js`, '--host', '127.0.0.1', '--port', '0',
  ], {
    cwd: frontend,
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  origin = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Vite startup timed out: ${output}`)), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    devServer.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
  if (evidence) await mkdir(evidence, { recursive: true });
});

test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

test.beforeEach(async ({ page }) => {
  // Do not send even synthetic app traffic to external services or a dev API.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort('blockedbyclient');
    if (url.pathname.startsWith('/synthetic/')) {
      if (url.pathname === '/synthetic/broken.svg') return route.fulfill({ status: 404, body: '' });
      return route.fulfill({ contentType: 'image/svg+xml', body: syntheticSvg });
    }
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json: [] });
    return route.continue();
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
});

for (const theme of ['hyrule', 'vigil']) {
  test(`smooth static icons at actual CSS sizes on ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 1000 });
    await page.goto(`${origin}/e2e/catalog-icons-fixture.html?theme=${theme}`);
    for (const size of [32, 40, 64, 96]) {
      const section = page.getByRole('region', { name: `${size}px icons` });
      const images = section.getByRole('img');
      await expect(images).toHaveCount(6);
      for (const image of await images.all()) {
        await image.scrollIntoViewIfNeeded();
        await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth)).toBe(256);
        expect(await image.evaluate((element) => ({
          width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height,
          rendering: getComputedStyle(element).imageRendering, animation: getComputedStyle(element).animationName,
        }))).toEqual({ width: size, height: size, rendering: 'auto', animation: 'none' });
      }
      expect(new Set(await images.evaluateAll((elements) => elements.map((element) => element.src))).size).toBe(6);
    }
    if (evidence) await page.screenshot({ path: `${evidence}/sizes-${theme}.png`, fullPage: true });
  });
}

test('all 160 imported PNGs decode in the browser', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 1600 });
  await page.goto(`${origin}/e2e/catalog-icons-fixture.html?all=1`);
  const images = page.getByRole('region', { name: 'Every imported catalog image' }).getByRole('img');
  await expect(images).toHaveCount(160);
  await images.evaluateAll((elements) => elements.forEach((element) => { element.loading = 'eager'; }));
  await expect.poll(() => images.evaluateAll((elements) => elements.filter((element) => element.complete && element.naturalWidth === 256 && element.naturalHeight === 256).length)).toBe(160);
  expect(new Set(await images.evaluateAll((elements) => elements.map((element) => element.src))).size).toBe(160);
  if (evidence) await page.getByRole('region', { name: 'Every imported catalog image' }).screenshot({ path: `${evidence}/all-160.png` });
});

test('failed PNGs retain legacy, base-species and labelled emoji fallbacks', async ({ page }) => {
  await page.route('**/abby-catalog-icons/**/objects/*.png*', (route) => route.request().resourceType() === 'image'
    ? route.fulfill({ status: 404, body: '' }) : route.fallback());
  await page.goto(`${origin}/e2e/catalog-icons-fixture.html`);
  const section = page.getByRole('region', { name: 'Fallback behavior' });
  for (const name of ['Recovered legacy', 'Recovered base', 'Unresolved record']) {
    const image = section.getByRole('img', { name, exact: true });
    await expect(image).toHaveAttribute('src', '/synthetic/legacy.svg');
    await expect.poll(() => image.evaluate((element) => element.naturalWidth)).toBe(256);
  }
  const emoji = section.getByRole('img', { name: 'Recovered emoji', exact: true });
  await expect(emoji).toHaveText('🍗');
  expect(await emoji.evaluate((element) => element.tagName)).toBe('SPAN');
  // A catalog import must not replace an animated gameplay consumer.
  const animation = section.getByRole('img', { name: 'Existing gameplay animation' });
  await expect(animation).toHaveCSS('animation-name', 'none');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(animation).toHaveCSS('animation-name', 'sprite-cycle');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  if (evidence) await section.screenshot({ path: `${evidence}/fallbacks.png` });
});

const catalogItems = [
  ['food-meat', 'Meat', 'food', 'chicken-leg', 'item-meat'],
  ['food-chicken-leg', 'Chicken Leg', 'food', 'chicken-leg', 'item-chicken-leg'],
  ['food-fish', 'Fish', 'food', 'cooked-fish', 'item-fish'],
  ['food-fish-cooked', 'Cooked Fish', 'food', 'cooked-fish', 'item-fish-cooked'],
  ['pouch-treasure', 'Treasure Hoard', 'coin_pouch', 'large-gold-coin-stack', 'item-pouch-treasure'],
  ['pouch-mega', 'Mega Hoard', 'coin_pouch', 'large-gold-coin-stack', 'item-pouch-mega'],
].map(([slug, name, item_type, sprite_key, catalog_icon], index) => ({
  id: index + 1, slug, name, item_type, sprite_key, catalog_icon,
  icon: '✨', rarity: 'common', rarity_display: 'Common', catalog_available: true,
}));
const challenge = {
  id: 1, name: 'Hoard Builder', quest_type: 'collection', quest_type_display: 'Collection',
  catalog_icon: 'challenge-hoard-builder', icon: '🏆', target_value: 10, duration_days: 7,
  reward_items: [{ id: 1, item_name: 'Mega Hoard', item_sprite_key: 'large-gold-coin-stack',
    item_catalog_icon: 'item-pouch-mega', item_icon: '💎', quantity: 1 }],
};
const hiddenItem = { id: 20, slug: 'streak-freeze', name: 'Streak Freeze',
  item_type: 'consumable', sprite_key: 'ice-crystal', catalog_icon: 'item-streak-freeze',
  icon: '❄️', rarity: 'rare', rarity_display: 'Rare', catalog_available: true };

async function syntheticApp(page, theme) {
  await page.addInitScript(() => {
    // Synthetic local identity only. Every API is intercepted before navigation.
    localStorage.setItem('abby_auth_token', 'synthetic-catalog-browser-only');
    localStorage.setItem('avatar_hint_count', '3');
    localStorage.removeItem('manage:codex:active-section');
  });
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
    const path = new URL(route.request().url()).pathname;
    const responses = {
      '/api/auth/me/': { id: 99, username: 'catalog-fixture', display_name: 'Local reviewer',
        role: 'parent', theme, family: { id: 1, name: 'Synthetic local family' } },
      '/api/pulse/': { unread_count: 0, notifications: [], recent_drops: [], active_quest: null,
        companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [], newly_unlocked_lorebook: [],
        header: { active_timer: null, coin_balance: 0, streak_days: 0 } },
      '/api/sprites/catalog/': { etag: 'synthetic-only', sprites: {} },
      '/api/items/catalog/': catalogItems,
      '/api/pets/species/catalog/': [],
      '/api/quests/catalog/': [challenge],
      '/api/inventory/': [...catalogItems, hiddenItem].map((item) => ({ id: item.id, item, quantity: 1 })),
      '/api/character/': {},
    };
    return route.fulfill({ json: responses[path] ?? [] });
  });
}

for (const theme of ['hyrule', 'vigil']) {
  test(`actual catalog, detail and inventory preserve content identities on ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await syntheticApp(page, theme);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`${origin}/codex`);
    await expect(page.getByRole('heading', { name: 'Content Catalog', exact: true })).toBeVisible();
    const urls = [];
    for (const item of catalogItems) {
      const image = page.getByRole('img', { name: item.name, exact: true });
      await image.scrollIntoViewIfNeeded();
      await expect.poll(() => image.evaluate((element) => element.naturalWidth)).toBe(256);
      expect((await image.boundingBox()).width).toBe(40);
      urls.push(await image.getAttribute('src'));
    }
    expect(new Set(urls).size).toBe(6);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    if (evidence) await page.screenshot({ path: `${evidence}/app-catalog-${theme}.png`, fullPage: true });

    await page.getByRole('button', { name: /Meat Common/ }).click();
    const detail = page.getByRole('dialog');
    await expect(detail).toBeVisible();
    const image = detail.getByRole('img', { name: 'Meat', exact: true });
    await expect.poll(() => image.evaluate((element) => element.naturalWidth)).toBe(256);
    expect((await image.boundingBox()).width).toBe(64);
    expect(await image.getAttribute('src')).toBe(urls[0]);
    if (evidence) await page.screenshot({ path: `${evidence}/app-detail-${theme}.png` });
    await page.getByRole('button', { name: 'Close', exact: true }).click();

    await page.getByRole('tab', { name: /Challenges, 1 entries/ }).click();
    await page.getByRole('button', { name: /Hoard Builder/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    const reward = page.getByRole('dialog').getByRole('img', { name: 'Mega Hoard', exact: true });
    await expect.poll(() => reward.evaluate((element) => element.naturalWidth)).toBe(256);
    expect(await reward.getAttribute('src')).toBe(urls[5]);
    if (evidence) await page.screenshot({ path: `${evidence}/app-challenge-${theme}.png` });

    await page.goto(`${origin}/treasury?tab=satchel`);
    for (const item of catalogItems.slice(0, 4)) {
      const inventoryImage = page.getByRole('img', { name: item.name, exact: true });
      await inventoryImage.scrollIntoViewIfNeeded();
      await expect.poll(() => inventoryImage.evaluate((element) => element.naturalWidth)).toBe(256);
      expect(await inventoryImage.getAttribute('src')).toBe(urls[item.id - 1]);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    if (evidence) await page.screenshot({ path: `${evidence}/app-inventory-${theme}.png`, fullPage: true });
    await page.getByRole('tab', { name: /Single-use Items/ }).click();
    const hiddenImage = page.getByRole('img', { name: hiddenItem.name, exact: true });
    await expect.poll(() => hiddenImage.evaluate((element) => element.naturalWidth)).toBe(256);
    expect(errors).toEqual([]);
  });
}

const rosterInventory = JSON.parse(readFileSync(new URL('../../contracts/api/fixtures/inventory-roster-hatching.json', import.meta.url), 'utf8'));

for (const [theme, width] of [['hyrule', 320], ['vigil', 375]]) {
  test(`Hatchery previews the selected family without mutations on ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    await syntheticApp(page, theme);
    const mutations = [];
    await page.route((url) => ['/api/inventory/', '/api/pets/stable/', '/api/pets/incubations/'].includes(url.pathname), async (route) => {
      const request = route.request(), path = new URL(request.url()).pathname;
      if (request.method() !== 'GET') {
        mutations.push({ path, method: request.method(), body: request.postDataJSON() });
        return route.fulfill({ status: 400, json: { detail: 'Preview must not hatch a pet.' } });
      }
      return route.fulfill({ json: path === '/api/inventory/' ? rosterInventory
        : path === '/api/pets/incubations/' ? { incubation: null, duration_seconds: 7200, server_now: '2026-10-18T10:00:00Z' }
          : { pets: [], mounts: [], total_possible: 15 } });
    });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`${origin}/bestiary?tab=hatchery`);
    await chooseDropdown(page.getByRole('combobox', { name: 'Egg', exact: true }), '91');
    await chooseDropdown(page.getByRole('combobox', { name: 'Potion', exact: true }), '52');
    const guide = page.getByRole('list', { name: 'Pet growth stages' });
    for (const label of ['Baby · Bat', 'Middle · Vampire Bat', 'Grown · Bat Lord']) {
      await expect(guide.getByText(label, { exact: true })).toBeVisible();
    }
    const steps = guide.getByRole('listitem');
    await expect(steps.first()).toHaveAttribute('aria-current', 'step');
    await expect(steps.nth(1)).not.toHaveAttribute('aria-current');
    await expect(page.getByRole('button', { name: 'Start incubation', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Hatch pet', exact: true })).toHaveCount(0);
    expect(mutations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    expect(errors).toEqual([]);
    if (evidence) await page.screenshot({ path: `${evidence}/hatchery-family-${theme}.png`, fullPage: true });
  });
}
