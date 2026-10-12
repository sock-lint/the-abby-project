import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;
const privateArt = existsSync(fileURLToPath(new URL('../src/companion/licensed/manifest.json', import.meta.url)));
const user = { id: 901, username: 'prototype-child', role: 'child', first_name: 'Prototype child', theme: 'hyrule' };
const chick = {
  id: 902, species: { name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐥', food_preference: 'Birdseed' },
  potion: { name: 'Base', slug: 'base', rarity: 'common' },
  is_active: true, growth_points: 85, evolved_to_mount: false, happiness_level: 'happy',
};

test.beforeAll(async () => {
  devServer = spawn(process.execPath, [
    fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)),
    '--host', '127.0.0.1', '--port', '0',
  ], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Companion fixture startup timed out.')), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Fixture exited (${code}).`)); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
});

test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

async function fixture(page, pet = chick) {
  const mutations = [];
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-browser-profile-session'));
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    // Vite source modules also contain /src/api/. Only mock real API routes.
    if (!path.startsWith('/api/')) return route.continue();
    if (request.method() !== 'GET') mutations.push(request.url());
    const responses = {
      '/api/auth/me/': user,
      '/api/character/': { ...user, display_name: 'Prototype child', level: 3, login_streak: 2, longest_login_streak: 3, perfect_days_count: 1 },
      '/api/cosmetics/': {}, '/api/cosmetics/catalog/': {},
      '/api/achievements/summary/': { badges_earned: [] },
      '/api/pets/stable/': { pets: [pet], mounts: [], total_possible: 94 },
      '/api/sprites/catalog/': {},
      '/api/push/config/': { enabled: false, public_key: '' },
      '/api/pulse/': { unread_count: 0, notifications: [], recent_drops: [], active_quest: null,
        companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [], newly_unlocked_lorebook: [],
        header: { active_timer: null, coin_balance: 0, streak_days: 0 } },
    };
    if (path.includes('pending-celebration')) return route.fulfill({ status: 204 });
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(responses[path] ?? []) });
  });
  return mutations;
}

test('profile, pet controls and greetings work at phone width without awards', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const mutations = await fixture(page);
  await page.goto(`${origin}/profile`);
  await expect(page.getByRole('heading', { name: 'Prototype child', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Base Chick', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Say hello', exact: true }).click();
  await expect(page.getByText('Hello, Base Chick! A little greeting, just for fun.')).toBeVisible();
  expect(mutations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('profile-phone.png'), fullPage: true });
  await page.getByRole('link', { name: 'Care & choose pets' }).click();
  await expect(page.getByRole('tablist', { name: 'Pets sections' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Companion actions' }).getByRole('link', { name: 'Inventory', exact: true })).toBeVisible();
});

test('an unsupported earned species keeps its own identity and 2D view', async ({ page }) => {
  await fixture(page, { ...chick, species: { name: 'Fox', slug: 'fox', sprite_key: 'fox', icon: '🦊' } });
  await page.goto(`${origin}/sigil`);
  await expect(page.getByRole('heading', { name: 'Base Fox', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Show 3D view' })).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Base Fox' })).toBeVisible();
});

test('owned Chick renders, survives context loss and remounts with working controls', async ({ page }) => {
  test.skip(!privateArt, 'Owned private exports are intentionally absent from public CI.');
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const mutations = await fixture(page);
  await page.goto(`${origin}/sigil`);
  await page.getByRole('button', { name: 'Show 3D view' }).click();
  await expect(page.locator('.companion-preview-stage')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.companion-preview canvas')).toBeVisible();
  await page.getByRole('checkbox', { name: 'Animate companion' }).check();
  await page.screenshot({ path: test.info().outputPath('chick-woodland.png') });
  await page.locator('.companion-preview canvas').evaluate((canvas) => {
    const gl = canvas.getContext('webgl2');
    gl.getExtension('WEBGL_lose_context').loseContext();
  });
  await expect(page.getByText(/The 3D view could not load/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Care & choose pets' })).toBeVisible();
  await page.getByRole('button', { name: 'Retry 3D view' }).click();
  await expect(page.locator('.companion-preview canvas')).toBeVisible();
  await expect(page.locator('.companion-preview-stage')).toHaveAttribute('aria-busy', 'false');
  await page.getByRole('button', { name: 'Use 2D view' }).click();
  await expect(page.locator('.companion-preview canvas')).toHaveCount(0);
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});

test('a broken model request leaves the profile and pet controls available', async ({ page }) => {
  test.skip(!privateArt, 'Owned private exports are intentionally absent from public CI.');
  await fixture(page);
  await page.route('**/*.glb*', (route) =>
    route.request().resourceType() === 'fetch' ? route.abort() : route.continue());
  await page.goto(`${origin}/sigil`);
  await page.getByRole('button', { name: 'Show 3D view' }).click();
  await expect(page.getByText(/The 3D view could not load/)).toBeVisible();
  await expect(page.getByRole('img', { name: 'Base Chick' })).toBeVisible();
  await page.getByRole('link', { name: 'Care & choose pets' }).click();
  await expect(page.getByRole('tablist', { name: 'Pets sections' })).toBeVisible();
});
