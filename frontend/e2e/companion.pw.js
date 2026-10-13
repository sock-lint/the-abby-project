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
  catalog_available: true,
  id: 902, name: 'Peep', species: { id: 941, name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐥', food_preference: 'Birdseed' },
  potion: { id: 942, name: 'Base', slug: 'base', rarity: 'common' },
  is_active: true, growth_points: 85, evolved_to_mount: false, happiness_level: 'happy',
};
const avatarDefaults = { hair_style: 'hair-01', hair_color: 'dark', skin_tone: 'fair', outfit: 'nature' };
const avatarOptions = {
  hair_style: ['hair-01', 'hair-02', 'hair-03', 'hair-04'],
  hair_color: ['light', 'dark'], skin_tone: ['fair', 'tan'], outfit: ['aqua', 'nature', 'fire', 'dark'],
};
const food = { id: 903, item: { id: 904, name: 'Birdseed', icon: '🌾', sprite_key: 'food-birdseed', item_type: 'food' }, quantity: 3 };
test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });

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

async function fixture(page, pet = chick, { mounts = [] } = {}) {
  const mutations = [];
  let ownedPet = { ...pet };
  const ownedMounts = [...mounts];
  let inventory = [{ ...food }];
  let character = {
    id: 906, username: user.username, display_name: 'Prototype child', level: 3,
    login_streak: 2, longest_login_streak: 3, perfect_days_count: 1,
    active_frame: null, active_title: null, active_theme: null, active_pet_accessory: null,
    active_trophy_badge: null, avatar_preferences: { ...avatarDefaults },
  };
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-browser-profile-session'));
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    // Vite source modules also contain /src/api/. Only mock real API routes.
    if (!path.startsWith('/api/')) return route.continue();
    if (request.method() !== 'GET') {
      const body = request.postDataJSON();
      mutations.push({ url: request.url(), method: request.method(), body });
      if (path === '/api/character/avatar/' && request.method() === 'POST') {
        const preferences = body?.avatar_preferences;
        const valid = body && Object.keys(body).length === 1 && preferences && !Array.isArray(preferences)
          && typeof preferences === 'object'
          && Object.entries(preferences).every(([key, value]) => avatarOptions[key]?.includes(value));
        if (!valid) return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'Unsupported avatar appearance.' }) });
        character = { ...character, avatar_preferences: { ...avatarDefaults, ...preferences } };
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(character) });
      }
      if (path === `/api/pets/${ownedPet.id}/feed/` && request.method() === 'POST') {
        if (body?.food_item_id !== food.item.id || ownedPet.evolved_to_mount) return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'This food cannot be used.' }) });
        ownedPet = { ...ownedPet, growth_points: 100, evolved_to_mount: true };
        ownedMounts.push({ id: 905, species: ownedPet.species, potion: ownedPet.potion, is_active: false, can_breed: true, breeding_cooldown_seconds: 0, last_bred_at: null, active_expedition: null });
        inventory = [{ ...food, quantity: food.quantity - 1 }];
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ growth_added: 15, new_growth: 100, evolved: true, mount_id: 905 }) });
      }
    }
    const responses = {
      '/api/auth/me/': user,
      '/api/character/': character,
      '/api/cosmetics/': {}, '/api/cosmetics/catalog/': {},
      '/api/achievements/summary/': { badges_earned: [] },
      '/api/pets/stable/': { pets: [ownedPet], mounts: ownedMounts, total_possible: 1, breeding_available: false },
      '/api/inventory/': inventory,
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

test('profile has its Archer character and saves appearance without companion or reward actions', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const mutations = await fixture(page);
  await page.goto(`${origin}/profile`);
  await expect(page.getByRole('heading', { name: 'Prototype child', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Upload picture', exact: true })).toBeVisible();
  await expect(page.getByText('Memory Meadow', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Change color theme' })).toHaveAttribute('href', '/settings#appearance');
  await expect(page.getByRole('tab', { name: /Covers/ })).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Your Archer character' })).toBeVisible();
  await expect(page.locator('.companion-preview')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Say hello', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Customize character' }).click();
  await expect(page.getByRole('combobox', { name: 'Hair style' })).toHaveValue('hair-01');
  await page.getByRole('combobox', { name: 'Hair style' }).selectOption('hair-04');
  await page.getByRole('combobox', { name: 'Hair color' }).selectOption('light');
  await page.getByRole('combobox', { name: 'Skin tone' }).selectOption('tan');
  await page.getByRole('combobox', { name: 'Outfit' }).selectOption('fire');
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Save character' }).click();
  await expect(page.getByText('Character saved.', { exact: true })).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/character/avatar/`, method: 'POST', body: {
    avatar_preferences: { hair_style: 'hair-04', hair_color: 'light', skin_tone: 'tan', outfit: 'fire' },
  } }]);
  await page.reload();
  await page.getByRole('button', { name: 'Customize character' }).click();
  await expect(page.getByRole('combobox', { name: 'Hair style' })).toHaveValue('hair-04');
  await expect(page.getByRole('combobox', { name: 'Outfit' })).toHaveValue('fire');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('profile-phone.png'), fullPage: true });
});

test('the pet home opens real care controls at phone width and feeds only on explicit food selection', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const mutations = await fixture(page);
  await page.goto(`${origin}/pets`);
  await expect(page.getByRole('tablist', { name: 'Pets sections' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Peep', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Show 3D view' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Say hello to Peep' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Peep is happy to see you.' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Care for Peep' })).toHaveCount(0);
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  const care = page.getByRole('dialog', { name: 'Care for Peep' });
  await expect(care).toBeVisible();
  await expect(care.getByRole('button', { name: /Birdseed/ })).toBeVisible();
  expect(mutations).toEqual([]);
  await care.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(care).toHaveCount(0);
  expect(mutations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  await care.getByRole('button', { name: /Birdseed/ }).click();
  await expect(page.getByRole('alertdialog')).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/pets/902/feed/`, method: 'POST', body: { food_item_id: 904 } }]);
});

test('an unsupported earned species keeps its own identity and 2D view', async ({ page }) => {
  const mutations = await fixture(page, { ...chick, catalog_available: false, name: 'Juniper', species: { name: 'Fox', slug: 'fox', sprite_key: 'fox', icon: '🦊', catalog_available: false } });
  await page.goto(`${origin}/bestiary`);
  const saved = page.getByRole('region', { name: 'Saved collection' });
  await expect(saved).toBeVisible();
  await expect(page.getByRole('button', { name: 'Show 3D view' })).toHaveCount(0);
  await expect(page.locator('.companion-preview')).toHaveCount(0);
  await expect(saved.getByRole('img', { name: 'Base Fox' })).toBeVisible();
  await saved.getByRole('button', { name: 'Care for Base Fox' }).click();
  await expect(page.getByRole('dialog', { name: 'Care for Juniper' })).toBeVisible();
  expect(mutations).toEqual([]);
});

test('owned Chick renders, survives context loss and remounts with working controls', async ({ page }) => {
  test.skip(!privateArt, 'Owned private exports are intentionally absent from public CI.');
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const mutations = await fixture(page);
  await page.goto(`${origin}/pets`);
  await expect(page.locator('.companion-preview-stage')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.companion-preview canvas')).toBeVisible();
  await page.locator('.companion-view-settings summary').click();
  await expect(page.getByRole('checkbox', { name: 'Animate companion' })).toBeChecked();
  await expect(page.getByRole('button', { name: '3D woodland' })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('.companion-view-settings summary').click();
  await page.screenshot({ path: test.info().outputPath('chick-woodland.png') });
  await page.locator('.companion-preview canvas').evaluate((canvas) => {
    const gl = canvas.getContext('webgl2');
    gl.getExtension('WEBGL_lose_context').loseContext();
  });
  await expect(page.getByText(/The 3D view could not load/)).toBeVisible();
  await expect(page.getByRole('img', { name: 'Peep, your companion' })).toBeVisible();
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  const care = page.getByRole('dialog', { name: 'Care for Peep' });
  await expect(care).toBeVisible();
  await care.getByRole('button', { name: 'Close', exact: true }).click();
  await page.locator('.companion-view-settings summary').click();
  await page.getByRole('button', { name: 'Retry 3D woodland' }).click();
  await expect(page.locator('.companion-preview canvas')).toBeVisible();
  await expect(page.locator('.companion-preview-stage')).toHaveAttribute('aria-busy', 'false');
  await page.getByRole('button', { name: '2D portrait' }).click();
  await expect(page.locator('.companion-preview canvas')).toHaveCount(0);
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});

test('a broken model request leaves pet care available and can retry without awarding anything', async ({ page }) => {
  test.skip(!privateArt, 'Owned private exports are intentionally absent from public CI.');
  const mutations = await fixture(page);
  await page.route('**/*.glb*', (route) =>
    route.request().resourceType() === 'fetch' ? route.abort() : route.continue());
  await page.goto(`${origin}/pets`);
  await expect(page.getByText(/The 3D view could not load/)).toBeVisible();
  await expect(page.getByRole('img', { name: 'Peep, your companion' })).toBeVisible();
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  const care = page.getByRole('dialog', { name: 'Care for Peep' });
  await expect(care.getByRole('button', { name: /Birdseed/ })).toBeVisible();
  await care.getByRole('button', { name: 'Close', exact: true }).click();
  await page.unroute('**/*.glb*');
  await page.locator('.companion-view-settings summary').click();
  await page.getByRole('button', { name: 'Retry 3D woodland' }).click();
  await expect(page.locator('.companion-preview canvas')).toBeVisible();
  await expect(page.locator('.companion-preview-stage')).toHaveAttribute('aria-busy', 'false');
  expect(mutations).toEqual([]);
});

test('owned mounts open their expedition choices without starting a run on entry', async ({ page }) => {
  const mount = { id: 905, species: chick.species, potion: chick.potion, catalog_available: true, is_active: true, can_breed: false, breeding_cooldown_seconds: 0, last_bred_at: null, active_expedition: null };
  const mutations = await fixture(page, { ...chick, evolved_to_mount: true, growth_points: 100 }, { mounts: [mount] });
  await page.goto(`${origin}/bestiary?tab=mounts`);
  await expect(page.getByRole('button', { name: 'Show 3D view' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Say hello to Peep' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Choose an expedition' }).click();
  await expect(page.getByRole('dialog', { name: 'Send Chick on an expedition' })).toBeVisible();
  expect(mutations).toEqual([]);
});

test('supplied Chick and Bird interactions stay local and usable after disabling motion', async ({ page }) => {
  test.skip(!privateArt, 'Owned private exports are intentionally absent from public CI.');
  await page.setViewportSize({ width: 375, height: 812 });
  const failures = [];
  page.on('pageerror', (error) => failures.push(error.message));
  const mutations = await fixture(page);
  await page.goto(`${origin}/pets`);
  await expect(page.getByRole('button', { name: 'Hop together' })).toBeEnabled();
  await page.getByRole('button', { name: 'Hop together' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Peep hops along with you.' })).toBeVisible();
  await page.getByRole('button', { name: 'Look around' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Peep looks around the clearing with you.' })).toBeVisible();
  await page.getByRole('button', { name: 'Look around' }).click();
  await page.locator('.companion-view-settings summary').click();
  await page.getByRole('checkbox', { name: 'Animate companion' }).uncheck();
  await page.locator('.companion-view-settings summary').click();
  await page.getByRole('button', { name: 'Say hello' , exact: true }).click();
  expect(mutations).toEqual([]);
  expect(failures).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('chick-play.png'), fullPage: true });
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  await page.getByRole('dialog').getByRole('button', { name: /Birdseed/ }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: /^Continue/ }).click();
  await expect(page.getByRole('button', { name: 'Fly together' })).toBeEnabled();
  await page.getByRole('button', { name: 'Fly together' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Peep stretches their wings' })).toBeVisible();
  expect(mutations).toHaveLength(1);
  expect(failures).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('bird-play.png'), fullPage: true });
});
