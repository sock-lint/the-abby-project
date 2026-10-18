import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers.js';

let server, origin;
const evidence = join(homedir(), '.local/state/abby-desktop-chats/rpg-rarity-progression/browser');
test.use({ reducedMotion: 'reduce', serviceWorkers: 'block' });
test.setTimeout(60_000);

test.beforeAll(async () => {
  await mkdir(evidence, { recursive: true });
  server = spawn(process.execPath, ['--input-type=module', '-e', "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: 0, hmr: false, watch: null } }); await server.listen(); server.printUrls();"], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Reward fixture startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Reward fixture exited ${code}: ${output}`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const address = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (address) { clearTimeout(timer); resolve(address[0]); }
    });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

for (const theme of ['hyrule', 'vigil']) for (const width of [320, 375]) {
  test(`reward guidance fits ${width}px on ${theme} without writes`, async ({ page }) => {
    const writes = [], external = [], errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('**/*', async (route) => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== origin) { external.push(request.url()); return route.abort(); }
      if (url.pathname.startsWith('/src/avatar/shared/') || /\.(?:glb|png|webp)(?:$|\?)/.test(url.pathname)) return route.abort();
      if (!url.pathname.startsWith('/api/')) return route.continue();
      if (request.method() !== 'GET') writes.push({ path: url.pathname, method: request.method() });
      const item = { id: 8, name: 'Fixture berries', item_type: 'food', rarity: 'rare', icon: '🫐', sprite_key: 'fixture-food', catalog_available: true, effect_summary: 'Adds 10 growth, plus 10 more for a pet that prefers this food.' };
      const payloads = {
        '/api/auth/me/': { id: 2, username: 'synthetic-rarity', display_name: 'Fixture child', role: 'child', theme, family: { id: 1, name: 'Synthetic family' } },
        '/api/pets/stable/': { pets: [{ id: 1, name: 'Moss', species: { id: 99, name: 'Fixture pet', slug: 'fixture-pet', sprite_key: 'fixture-pet', icon: '🐾', catalog_available: true }, potion: { id: 1, name: 'Base', slug: 'base', rarity: 'common', catalog_available: true }, growth_points: 25, is_active: true, evolved_to_mount: false }], mounts: [], total_possible: 1 },
        '/api/inventory/': [{ id: 1, quantity: 2, updated_at: '2026-10-17T12:00:00Z', item }],
        '/api/character/': { active_boosts: [] },
      };
      return route.fulfill({ json: payloads[url.pathname] ?? [] });
    });
    await page.setViewportSize({ width, height: 568 });
    const open = async (view) => page.goto(`${origin}/e2e/reward-rarity-fixture.html?theme=${theme}&view=${view}`);
    const capture = async (view) => {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: join(evidence, `${theme}-${width}-${view}.png`), fullPage: true });
    };

    await open('badge');
    await page.getByRole('button', { name: /Fixture milestone/ }).click();
    const badge = page.getByRole('dialog', { name: 'Fixture milestone' });
    await expect(badge.getByText('Base coin bonus')).toBeVisible();
    await expect(badge.getByText('+35 coins')).toBeVisible();
    await capture('badge');

    await open('goal');
    await expect(page.getByText('Fixture progress frame ×1')).toBeVisible();
    await expect(page.getByText('epic', { exact: true })).toBeVisible();
    await expect(page.getByText('An earned frame to choose for your profile.')).toBeVisible();
    await expect(page.locator('img[src^="data:image/svg+xml"]')).toBeVisible();
    await capture('goal');

    await open('drop');
    await page.getByRole('button', { name: 'Show rare reward' }).click();
    const action = page.getByRole('link', { name: 'Choose profile frame' });
    await action.scrollIntoViewIfNeeded();
    const bounds = await action.boundingBox();
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await capture('drop');
    await action.click();
    await expect(page.getByLabel('Fixture location')).toHaveText('/sigil');
    await expect(page.getByRole('alertdialog')).toHaveCount(0);

    await open('food');
    await page.getByRole('button', { name: 'Care for Base Fixture pet', exact: true }).click();
    const food = page.getByRole('button', { name: /Fixture berries/ });
    await expect(food.getByText('Adds 10 growth, plus 10 more for a pet that prefers this food.')).toBeVisible();
    expect((await food.boundingBox()).height).toBeGreaterThanOrEqual(44);
    await capture('food');

    await open('inventory');
    await expect(page.getByText('Fixture berries', { exact: true })).toBeVisible();
    await chooseDropdown(page.getByRole('combobox', { name: 'Rarity' }), 'rare');
    await chooseDropdown(page.getByRole('combobox', { name: 'Sort items' }), 'rarity');
    await expect(page.getByText('Adds 10 growth, plus 10 more for a pet that prefers this food.')).toBeVisible();
    await capture('inventory');

    await open('expedition');
    await page.getByRole('button', { name: 'Show expedition rewards' }).click();
    await expect(page.getByText('rare', { exact: true })).toBeVisible();
    await expect(page.getByText('epic', { exact: true })).toBeVisible();
    await expect(page.getByText('Duplicate exchanged for 25 coins')).toBeVisible();
    await page.getByRole('button', { name: 'Continue', exact: true }).scrollIntoViewIfNeeded();
    await capture('expedition');
    expect(writes).toEqual([]);
    expect(external).toEqual([]);
    expect(errors).toEqual([]);
  });
}
