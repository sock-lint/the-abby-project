import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import playwrightUtils from 'playwright-core/lib/utilsBundle';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;
const privateArt = existsSync(fileURLToPath(new URL('../src/companion/licensed/manifest.json', import.meta.url)));
const avatarManifestPath = fileURLToPath(new URL('../src/avatar/licensed/manifest.json', import.meta.url));
const avatarSchema = existsSync(avatarManifestPath) ? JSON.parse(readFileSync(avatarManifestPath, 'utf8')).schema_version : null;
const privateAvatarArt = [2, 3].includes(avatarSchema);
const privateWardrobeArt = avatarSchema === 3;
const avatarCatalog = JSON.parse(readFileSync(fileURLToPath(new URL('../../contracts/api/fixtures/avatar-catalog.json', import.meta.url)), 'utf8'));
const archer = avatarCatalog.avatars.find((avatar) => avatar.id === 'female-archer');
const { PNG } = playwrightUtils;
const sky = JSON.parse(readFileSync(fileURLToPath(new URL('../src/storybook/presentation.json', import.meta.url)), 'utf8')).palette.sky;
const skyRgb = [1, 3, 5].map((index) => Number.parseInt(sky.slice(index, index + 2), 16));

async function archerCapture(canvas, path) {
  const bytes = await canvas.screenshot({ path, style: '[data-journal-sticky-header], [data-journal-bottom-nav], [role="tooltip"] { visibility: hidden !important; }' });
  const frame = PNG.sync.read(bytes);
  let colored = 0;
  let sampled = 0;
  // Inspect the center of the canvas, excluding rounded borders and DOM
  // overlays. A ready-but-empty sky cannot establish an Archer rendering pass.
  for (let y = Math.floor(frame.height * 0.15); y < frame.height * 0.9; y += 1) {
    for (let x = Math.floor(frame.width * 0.2); x < frame.width * 0.8; x += 1) {
      const offset = (y * frame.width + x) * 4;
      sampled += 1;
      if (skyRgb.some((value, channel) => Math.abs(frame.data[offset + channel] - value) > 12)) colored += 1;
    }
  }
  expect(colored / sampled, 'The actual Archer must visibly occupy the canvas before its animation is validated.').toBeGreaterThan(0.05);
  return createHash('sha256').update(bytes).digest('hex');
}
const user = { id: 901, username: 'prototype-child', role: 'child', first_name: 'Prototype child', theme: 'hyrule' };
const chick = {
  catalog_available: true,
  id: 902, name: 'Peep', species: { id: 941, name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐥', food_preference: 'Birdseed' },
  potion: { id: 942, name: 'Base', slug: 'base', rarity: 'common' },
  is_active: true, growth_points: 85, evolved_to_mount: false, happiness_level: 'happy',
};
const legacyBindings = Object.entries(archer.accessory_bindings).filter(([, binding]) => binding.legacy_preference_key);
const avatarDefaults = {
  ...archer.defaults.appearance,
  ...Object.fromEntries(legacyBindings.map(([slot, binding]) => [binding.legacy_preference_key, archer.defaults.accessories[slot]])),
};
function avatarConfiguration(preferences) {
  return {
    avatar_id: archer.id,
    appearance: Object.fromEntries(Object.entries(archer.defaults.appearance).map(([key, value]) => [key, preferences[key] ?? value])),
    accessories: {
      ...archer.defaults.accessories,
      ...Object.fromEntries(legacyBindings.map(([slot, binding]) => [slot, preferences[binding.legacy_preference_key] ?? archer.defaults.accessories[slot]])),
    },
  };
}
function legacyPreferences(configuration) {
  return { ...configuration.appearance,
    ...Object.fromEntries(legacyBindings.map(([slot, binding]) => [binding.legacy_preference_key, configuration.accessories[slot]])) };
}
const food = { id: 903, item: { id: 904, name: 'Birdseed', icon: '🌾', sprite_key: 'food-birdseed', item_type: 'food' }, quantity: 3 };
test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] }, actionTimeout: 15_000 });

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

async function fixture(page, pet = chick, { mounts = [], avatarPreferences = avatarDefaults } = {}) {
  const mutations = [];
  let ownedPet = { ...pet };
  const ownedMounts = [...mounts];
  let inventory = [{ ...food }];
  let character = {
    id: 906, username: user.username, display_name: 'Prototype child', level: 3,
    login_streak: 2, longest_login_streak: 3, perfect_days_count: 1,
    active_frame: null, active_title: null, active_theme: null, active_pet_accessory: null,
    active_trophy_badge: null, avatar_preferences: { ...avatarDefaults, ...avatarPreferences },
    avatar_configuration: avatarConfiguration(avatarPreferences),
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
      if (path === '/api/character/avatar/configuration/' && request.method() === 'POST') {
        const configuration = body?.avatar_configuration;
        const valid = body && Object.keys(body).length === 1 && configuration?.avatar_id === archer.id
          && Object.keys(configuration).length === 3
          && ['appearance', 'accessories'].every((scope) => configuration[scope] && typeof configuration[scope] === 'object' && !Array.isArray(configuration[scope])
            && Object.keys(configuration[scope]).length === Object.keys(archer.defaults[scope]).length
            && Object.keys(archer.defaults[scope]).every((key) => Object.hasOwn(configuration[scope], key)))
          && archer.groups.flatMap((group) => group.fields).every((field) => field.choices.some((choice) =>
            choice.value === configuration[field.accessory_slot ? 'accessories' : 'appearance'][field.key]));
        if (!valid) return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'Unsupported avatar appearance.' }) });
        character = { ...character, avatar_preferences: legacyPreferences(configuration), avatar_configuration: structuredClone(configuration) };
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
      '/api/character/': { ...character, avatar_preferences: { ...avatarDefaults, ...character.avatar_preferences } },
      '/api/character/avatar/catalog/': avatarCatalog,
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
  // This retained four-option record predates the three new identity fields.
  const mutations = await fixture(page, chick, { avatarPreferences: {
    hair_style: 'hair-01', hair_color: 'dark', skin_tone: 'fair', outfit: 'nature',
  } });
  await page.goto(`${origin}/profile`);
  await expect(page.getByRole('heading', { name: 'Prototype child', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Upload picture', exact: true })).toBeVisible();
  await expect(page.getByText('Memory Meadow', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Change color theme' })).toHaveAttribute('href', '/settings#appearance');
  await expect(page.getByRole('tab', { name: /Covers/ })).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Your Female Archer avatar' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Customize avatar' })).toHaveAttribute('href', '/profile/customize');
  await expect(page.getByRole('button', { name: 'Customize character' })).toHaveCount(0);
  await expect(page.locator('.companion-preview')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Say hello', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Customize avatar' }).click();
  await expect(page).toHaveURL(`${origin}/profile/customize`);
  await expect(page.getByRole('combobox', { name: 'Hairstyle' })).toHaveValue('hair-01');
  await expect(page.getByRole('combobox', { name: 'Outfit' })).toHaveValue('archer-01');
  await expect(page.getByRole('combobox', { name: 'Face', exact: true })).toHaveValue('face-01');
  await expect(page.getByRole('combobox', { name: 'Ears', exact: true })).toHaveValue('head-02');
  await page.getByRole('combobox', { name: 'Hairstyle' }).selectOption('hair-04');
  await page.getByRole('combobox', { name: 'Hair color' }).selectOption('light');
  await page.getByRole('combobox', { name: 'Skin tone' }).selectOption('tan');
  await page.getByRole('combobox', { name: 'Palette', exact: true }).selectOption('fire');
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Save avatar' }).click();
  await expect(page.getByText('Avatar saved.', { exact: true })).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/character/avatar/configuration/`, method: 'POST', body: {
    avatar_configuration: avatarConfiguration({ ...avatarDefaults, hair_style: 'hair-04', hair_color: 'light', skin_tone: 'tan', outfit: 'fire' }),
  } }]);
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Hairstyle' })).toHaveValue('hair-04');
  await expect(page.getByRole('combobox', { name: 'Palette', exact: true })).toHaveValue('fire');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('profile-phone.png'), fullPage: true });
});

test('expanded character identity saves and reloads every supplied choice without earning anything', async ({ page }) => {
  const mutations = await fixture(page);
  const preferences = {
    hair_style: 'hair-03', hair_color: 'orange', skin_tone: 'tan', outfit: 'aqua',
    outfit_style: 'archer-03', face_style: 'face-03', head_style: 'head-01',
  };
  await page.goto(`${origin}/profile`);
  await page.getByRole('link', { name: 'Customize avatar' }).click();
  const labels = { hair_style: 'Hairstyle', hair_color: 'Hair color', skin_tone: 'Skin tone', outfit: 'Palette', outfit_style: 'Outfit', face_style: 'Face', head_style: 'Ears' };
  for (const [key, value] of Object.entries(preferences)) {
    await page.getByRole('combobox', { name: labels[key], exact: true }).selectOption(value);
  }
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Save avatar' }).click();
  await expect(page.getByText('Avatar saved.', { exact: true })).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/character/avatar/configuration/`, method: 'POST', body: { avatar_configuration: avatarConfiguration({ ...avatarDefaults, ...preferences }) } }]);
  await page.reload();
  for (const [key, value] of Object.entries(preferences)) {
    await expect(page.getByRole('combobox', { name: labels[key], exact: true })).toHaveValue(value);
  }
  expect(mutations).toHaveLength(1);
});

test('wardrobe presets and individual None choices save at phone width without reward mutations', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const identity = { ...avatarDefaults, hair_style: 'hair-04', hair_color: 'grey', outfit_style: 'archer-03', face_style: 'face-03', head_style: 'head-01', skin_tone: 'tan' };
  const mutations = await fixture(page, chick, { avatarPreferences: identity });
  await page.goto(`${origin}/profile`);
  await page.getByRole('link', { name: 'Customize avatar' }).click();
  const wardrobe = page.getByRole('group', { name: 'Accessories', exact: true });
  await expect(wardrobe).toBeVisible();
  for (const label of ['Headwear', 'Face accessory', 'Left hand', 'Back accessory']) await expect(wardrobe.getByRole('combobox', { name: label, exact: true })).toHaveValue('none');
  await page.getByRole('group', { name: 'Coordinated looks', exact: true }).getByRole('button', { name: 'Dark', exact: true }).click();
  await expect(page.getByRole('group', { name: 'Coordinated looks', exact: true }).getByRole('button', { name: 'Dark', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('combobox', { name: 'Hairstyle' })).toHaveValue('hair-04');
  await expect(page.getByRole('combobox', { name: 'Outfit' })).toHaveValue('archer-03');
  await wardrobe.getByRole('combobox', { name: 'Left hand', exact: true }).selectOption('none');
  await expect(page.getByRole('group', { name: 'Coordinated looks', exact: true }).getByRole('button', { name: 'Dark', exact: true })).toHaveAttribute('aria-pressed', 'false');
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Save avatar' }).click();
  await expect(page.getByText('Avatar saved.', { exact: true })).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/character/avatar/configuration/`, method: 'POST', body: { avatar_configuration: avatarConfiguration({
    ...identity, outfit: 'dark', headwear_style: 'hood-mystical', mask_style: 'mask-undercover', quiver_style: 'quiver-tale',
  }) } }]);
  await page.reload();
  await expect(wardrobe.getByRole('combobox', { name: 'Headwear', exact: true })).toHaveValue('hood-mystical');
  await expect(wardrobe.getByRole('combobox', { name: 'Face accessory', exact: true })).toHaveValue('mask-undercover');
  await expect(wardrobe.getByRole('combobox', { name: 'Left hand', exact: true })).toHaveValue('none');
  await expect(wardrobe.getByRole('combobox', { name: 'Back accessory', exact: true })).toHaveValue('quiver-tale');
  for (const label of ['Headwear', 'Face accessory', 'Back accessory']) await wardrobe.getByRole('combobox', { name: label, exact: true }).selectOption('none');
  await page.getByRole('button', { name: 'Save avatar' }).click();
  await expect(page.getByText('Avatar saved.', { exact: true })).toBeVisible();
  expect(mutations).toHaveLength(2);
  expect(mutations[1].body.avatar_configuration).toEqual(avatarConfiguration({ ...identity, outfit: 'dark' }));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('wardrobe-phone-controls.png'), fullPage: true });
});

test('private Archer wardrobe renders supplied gear, retains Idle and restores saved selections', async ({ page }) => {
  test.skip(!privateWardrobeArt, 'Owned wardrobe exports are intentionally absent from public CI.');
  await page.setViewportSize({ width: 375, height: 812 });
  const failures = [];
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error' && /THREE\.WebGLProgram|VALIDATE_STATUS|ERROR:\s*\d/.test(message.text())) failures.push(message.text()); });
  const mutations = await fixture(page);
  await page.goto(`${origin}/profile`);
  const view = page.getByRole('group', { name: 'Character view' });
  const canvas = view.locator('canvas');
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('link', { name: 'Customize avatar' }).click();
  const wardrobe = page.getByRole('group', { name: 'Accessories', exact: true });
  for (const costume of ['archer-01', 'archer-02', 'archer-03']) {
    await page.getByRole('combobox', { name: 'Outfit' }).selectOption(costume);
    for (const preset of ['Aqua', 'Nature', 'Fire', 'Dark']) {
      await page.getByRole('group', { name: 'Coordinated looks', exact: true }).getByRole('button', { name: preset, exact: true }).click();
      await view.scrollIntoViewIfNeeded();
      await expect(view).toHaveAttribute('aria-busy', 'false');
      await expect(canvas).toBeVisible();
      await archerCapture(canvas, test.info().outputPath(`${costume}-wardrobe-${preset.toLowerCase()}.png`));
    }
  }
  // Compare deterministic reduced-motion captures within one palette. Adding
  // a real crown must change actual rendered pixels, not only the controls.
  for (const label of ['Headwear', 'Face accessory', 'Left hand', 'Back accessory']) await wardrobe.getByRole('combobox', { name: label, exact: true }).selectOption('none');
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  const bare = await archerCapture(canvas, test.info().outputPath('wardrobe-none.png'));
  await wardrobe.getByRole('combobox', { name: 'Headwear', exact: true }).selectOption('crown-eve');
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  expect(await archerCapture(canvas, test.info().outputPath('wardrobe-crown.png'))).not.toBe(bare);
  await wardrobe.getByRole('combobox', { name: 'Left hand', exact: true }).selectOption('bow-myth');
  await wardrobe.getByRole('combobox', { name: 'Back accessory', exact: true }).selectOption('quiver-tale');
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const first = await archerCapture(canvas);
  await expect.poll(() => archerCapture(canvas), { message: 'The fully equipped Archer must retain the supplied Idle.' }).not.toBe(first);
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Save avatar' }).click();
  await expect(page.getByText('Avatar saved.', { exact: true })).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/character/avatar/configuration/`, method: 'POST', body: { avatar_configuration: avatarConfiguration({
    ...avatarDefaults, outfit_style: 'archer-03', outfit: 'dark', headwear_style: 'crown-eve', bow_style: 'bow-myth', quiver_style: 'quiver-tale',
  }) } }]);
  await page.reload();
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await expect(canvas).toBeVisible();
  expect(mutations).toHaveLength(1);
  expect(failures).toEqual([]);
});

test('private Archer Idle renders moving skin, pauses for reduced motion and changes complete rigs locally', async ({ page }) => {
  test.skip(!privateAvatarArt, 'Schema 2 owned Archer exports are intentionally absent from public CI.');
  await page.setViewportSize({ width: 375, height: 812 });
  const failures = [];
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && /THREE\.WebGLProgram|VALIDATE_STATUS|ERROR:\s*\d/.test(message.text())) failures.push(message.text());
  });
  const mutations = await fixture(page);
  await page.goto(`${origin}/profile`);
  const view = page.getByRole('group', { name: 'Character view' });
  const canvas = view.locator('canvas');
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await expect(canvas).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeEnabled();
  await expect(view).toHaveAccessibleDescription(/Tap for an animation/);
  await expect(page.getByRole('button', { name: 'Play animation' })).toBeEnabled();
  const first = await archerCapture(canvas, test.info().outputPath('archer-idle-first.png'));
  await expect.poll(() => archerCapture(canvas), { message: 'The supplied Idle must change actual rendered canvas pixels.' }).not.toBe(first);
  await archerCapture(canvas, test.info().outputPath('archer-idle-moving.png'));
  expect(mutations).toEqual([]);

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.getByRole('button', { name: 'Play animation' })).toBeDisabled();
  await expect(page.getByText(/Animations are paused/)).toBeVisible();
  let previousCapture;
  let stableCaptures = 0;
  // Allow a previously requested WebGL frame to finish, then require three
  // consecutive stable rendered captures, not merely a disabled button.
  await expect.poll(async () => {
    const captured = await archerCapture(canvas);
    stableCaptures = captured === previousCapture ? stableCaptures + 1 : 0;
    previousCapture = captured;
    return stableCaptures;
  }, { intervals: [100, 250, 350], message: 'Reduced motion must settle and retain the same rendered pose.' }).toBe(3);
  expect(await archerCapture(canvas, test.info().outputPath('archer-idle-paused.png'))).toBe(previousCapture);

  await page.getByRole('link', { name: 'Customize avatar' }).click();
  let releaseRig;
  const rigReady = new Promise((resolve) => { releaseRig = resolve; });
  await page.route('**/archer-02.glb', async (route) => { await rigReady; await route.continue(); });
  try {
    await page.getByRole('combobox', { name: 'Outfit' }).selectOption('archer-02');
    await expect(view).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByText('Loading your avatar…')).toBeVisible();
  } finally { releaseRig(); }
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await page.unroute('**/archer-02.glb');
  await page.evaluate(() => {
    window.__abbyAvatarLoadingPhases = [];
    window.__abbyAvatarLoadingObserver = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'attributes' && record.target.getAttribute('aria-label') === 'Character view') {
          window.__abbyAvatarLoadingPhases.push({ before: record.oldValue, after: record.target.getAttribute('aria-busy') });
        }
      }
    });
    window.__abbyAvatarLoadingObserver.observe(document.querySelector('[data-avatar-preview]'), {
      subtree: true, attributes: true, attributeOldValue: true, attributeFilter: ['aria-busy'],
    });
  });
  await page.getByRole('combobox', { name: 'Ears', exact: true }).selectOption('head-01');
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await expect.poll(() => page.evaluate(() => window.__abbyAvatarLoadingPhases.some((phase) => phase.before === 'true' && phase.after === 'false'))).toBe(true);
  await page.evaluate(() => window.__abbyAvatarLoadingObserver.disconnect());
  await page.getByRole('combobox', { name: 'Hair color' }).selectOption('brown');
  await page.getByRole('combobox', { name: 'Face', exact: true }).selectOption('face-02');
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await archerCapture(canvas, test.info().outputPath('archer-outfit-2-rounded-face-2.png'));
  // Costume 3 contains the publisher's fifth influence on one vertex. Force
  // its actual shader to compile and render, retaining that all-weight pose.
  await page.getByRole('combobox', { name: 'Outfit' }).selectOption('archer-03');
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await expect(canvas).toBeVisible();
  await archerCapture(canvas, test.info().outputPath('archer-outfit-3-rounded-face-2.png'));
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await view.scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeEnabled();
  await expect(view).toHaveAccessibleDescription(/Tap for an animation/);
  const costume3First = await archerCapture(canvas);
  await expect.poll(() => archerCapture(canvas), { message: 'Costume 3 must animate with its complete original skin influences.' }).not.toBe(costume3First);
  await archerCapture(canvas, test.info().outputPath('archer-outfit-3-idle-moving.png'));
  expect(mutations).toEqual([]);
  await page.getByRole('button', { name: 'Save avatar' }).click();
  await expect(page.getByText('Avatar saved.', { exact: true })).toBeVisible();
  expect(mutations).toEqual([{ url: `${origin}/api/character/avatar/configuration/`, method: 'POST', body: {
    avatar_configuration: avatarConfiguration({ ...avatarDefaults, outfit_style: 'archer-03', head_style: 'head-01', hair_color: 'brown', face_style: 'face-02' }),
  } }]);
  await page.reload();
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('aria-busy', 'false');
  await expect(canvas).toBeVisible();
  expect(mutations).toHaveLength(1);
  expect(failures).toEqual([]);
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
  await page.getByRole('button', { name: 'Feed your companion' }).evaluate((button) => button.scrollIntoView({ block: 'center', behavior: 'instant' }));
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  const care = page.getByRole('dialog', { name: 'Care for Peep' });
  await expect(care).toBeVisible();
  await expect(care.getByRole('button', { name: /Birdseed/ })).toBeVisible();
  expect(mutations).toEqual([]);
  await care.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(care).toHaveCount(0);
  expect(mutations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Feed your companion' }).evaluate((button) => button.scrollIntoView({ block: 'center', behavior: 'instant' }));
  await page.getByRole('button', { name: 'Feed your companion' }).click();
  await expect(care).toBeVisible();
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
