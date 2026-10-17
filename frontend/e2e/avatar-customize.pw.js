import { chooseDropdown } from './dropdown-helpers.js';
import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, isAbsolute } from 'node:path';
import { stripVTControlCharacters } from 'node:util';
import playwrightUtils from 'playwright-core/lib/utilsBundle';

const catalogPath = fileURLToPath(new URL('../../contracts/api/fixtures/avatar-catalog.json', import.meta.url));
const profilePath = fileURLToPath(new URL('../../contracts/api/fixtures/character-avatar-default.json', import.meta.url));
const manifestPath = fileURLToPath(new URL('../src/avatar/licensed/manifest.json', import.meta.url));
const assetLock = JSON.parse(readFileSync(fileURLToPath(new URL('../assets.lock.json', import.meta.url)), 'utf8'));
const archerPin = assetLock.releases.find((entry) => entry.family_id === 'meshtint-female-archer-pack-01');
const sharedArcher = archerPin && fileURLToPath(new URL(`../src/avatar/shared/${archerPin.directory}/manifest.json`, import.meta.url));
const privateWardrobeArt = (existsSync(manifestPath) && JSON.parse(readFileSync(manifestPath, 'utf8')).schema_version === 3) || !!(sharedArcher && existsSync(sharedArcher));
const captureDirectory = process.env.ABBY_AVATAR_CUSTOMIZE_CAPTURE_DIR;
const { PNG } = playwrightUtils;
const sky = JSON.parse(readFileSync(fileURLToPath(new URL('../src/storybook/presentation.json', import.meta.url)), 'utf8')).palette.sky;
const skyRgb = [1, 3, 5].map((index) => Number.parseInt(sky.slice(index, index + 2), 16));
let devServer;
let origin;

test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] }, trace: 'off', actionTimeout: 15_000 });

test.beforeAll(async () => {
  // Real App/routes, synthetic local API state, and no Django/production access.
  devServer = spawn(process.execPath, [
    fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0',
  ], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Avatar fixture startup timed out.')), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Avatar fixture exited (${code}).`)); });
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

async function fixture(page, { unavailableAdapter = false } = {}) {
  const catalog = JSON.parse(readFileSync(catalogPath, 'utf8'));
  let definition = catalog.avatars.find((avatar) => avatar.id === catalog.default_avatar_id);
  if (unavailableAdapter) {
    // Synthetic future base: reuse global Archer equipment IDs on its OWN
    // illustrative sockets. This establishes UI reuse, never actual Knight fit.
    catalog.accessories['synthetic-sword'] = { label: 'Synthetic sword', source_pack: 'synthetic-knight' };
    catalog.accessories['synthetic-shield'] = { label: 'Synthetic shield', source_pack: 'synthetic-knight' };
    const bindings = {
      headwear: { item_ids: [], attachment: 'SyntheticHead' },
      face_accessory: { item_ids: [], attachment: 'SyntheticHead' },
      left_hand: { item_ids: ['bow-greenhorn', 'bow-vines', 'bow-myth', 'synthetic-shield'], attachment: 'SyntheticLeftPalm' },
      right_hand: { item_ids: ['synthetic-sword'], attachment: 'SyntheticRightPalm' },
      back: { item_ids: ['quiver-angel', 'quiver-rook', 'quiver-tale'], attachment: 'SyntheticBack' },
    };
    definition = {
      id: 'synthetic-knight', label: 'Knight', renderer_adapter: 'synthetic-knight',
      defaults: { appearance: { armor: 'synthetic-steel' }, accessories: Object.fromEntries(catalog.accessory_slots.map((slot) => [slot.id, 'none'])) },
      groups: [
        { id: 'appearance', label: 'Appearance', fields: [{ key: 'armor', label: 'Armor', choices: [{ value: 'synthetic-steel', label: 'Synthetic steel' }] }] },
        { id: 'accessories', label: 'Accessories', fields: catalog.accessory_slots.map((slot) => ({ key: slot.id, label: slot.label, accessory_slot: slot.id,
          choices: [{ value: 'none', label: 'None' }, ...bindings[slot.id].item_ids.map((id) => ({ value: id, accessory_id: id }))] })) },
      ],
      accessory_bindings: bindings, presets: [],
    };
    catalog.avatars.push(definition);
  }
  let profile = JSON.parse(readFileSync(profilePath, 'utf8'));
  if (unavailableAdapter) profile.avatar_configuration = { avatar_id: definition.id, ...structuredClone(definition.defaults) };
  const user = { id: profile.id, username: profile.username, first_name: 'Browser child', role: 'child', theme: 'hyrule' };
  const mutations = [];
  const modelRequests = [];
  let failNextSave = false;
  page.on('request', (request) => {
    const url = new URL(request.url());
    // Vite's ?import&url modules contain only URL strings, not model bytes.
    if (url.pathname.endsWith('.glb') && !url.searchParams.has('import')) modelRequests.push(request.url());
  });
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-avatar-editor-session'));
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    // No fixture traffic can reach another origin, including a proxy/API host.
    if (url.origin !== origin) return route.abort();
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (request.method() !== 'GET') {
      const body = request.postDataJSON();
      mutations.push({ path: url.pathname, method: request.method(), body });
      if (url.pathname !== '/api/character/avatar/configuration/' || request.method() !== 'POST') {
        return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'Unexpected synthetic fixture mutation.' }) });
      }
      if (failNextSave) {
        failNextSave = false;
        return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Synthetic save unavailable. Try again.' }) });
      }
      const configuration = body?.avatar_configuration;
      const avatar = catalog.avatars.find((item) => item.id === configuration?.avatar_id);
      const fields = avatar?.groups.flatMap((group) => group.fields) || [];
      const valid = body && Object.keys(body).length === 1 && avatar && configuration && Object.keys(configuration).length === 3
        && ['appearance', 'accessories'].every((scope) => configuration[scope]
          && Object.keys(configuration[scope]).length === Object.keys(avatar.defaults[scope]).length
          && Object.keys(avatar.defaults[scope]).every((key) => Object.hasOwn(configuration[scope], key)))
        && fields.every((field) => field.choices.some((choice) => choice.value === configuration[field.accessory_slot ? 'accessories' : 'appearance'][field.key]));
      if (!valid) return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'Unsupported avatar appearance.' }) });
      profile = { ...profile, avatar_configuration: structuredClone(configuration) };
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(profile) });
    }
    const responses = {
      '/api/auth/me/': user,
      '/api/character/': profile,
      '/api/character/avatar/catalog/': catalog,
      '/api/cosmetics/': {}, '/api/cosmetics/catalog/': {}, '/api/badges/': [],
      '/api/achievements/summary/': { badges_earned: [] },
      '/api/sprites/catalog/': {}, '/api/push/config/': { enabled: false, public_key: '' },
      '/api/clock/': { id: 910, status: 'active', clock_in: new Date(Date.now() - 45_000).toISOString(), clock_out: null },
      '/api/challenges/': { goals: [], pinned: null },
      '/api/pulse/': { unread_count: 0, notifications: [], recent_drops: [], active_quest: null,
        companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [], newly_unlocked_lorebook: [],
        header: { active_timer: null, coin_balance: 0, streak_days: 0 } },
    };
    if (url.pathname.includes('pending-celebration')) return route.fulfill({ status: 204 });
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(responses[url.pathname] ?? []) });
  });
  return { mutations, modelRequests, failSave: () => { failNextSave = true; }, saved: () => profile.avatar_configuration };
}

async function openEditor(page, options) {
  const state = await fixture(page, options);
  await page.goto(`${origin}/profile/customize`);
  await expect(page.getByRole('heading', { name: 'Customize avatar', exact: true })).toBeVisible();
  await expect(page.locator('[data-avatar-workspace]')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Quick actions/ })).toHaveCount(0);
  return state;
}

async function clearOfShell(page, locator) {
  await expect(locator).toBeInViewport({ ratio: 1 });
  const bounds = await locator.boundingBox();
  const viewport = page.viewportSize();
  expect(bounds.x).toBeGreaterThanOrEqual(-1);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width + 1);
  const header = await page.locator('[data-journal-sticky-header]').boundingBox();
  expect(bounds.y).toBeGreaterThanOrEqual(header.y + header.height - 1);
  const navigation = page.locator('[data-journal-bottom-nav]');
  const bottom = await navigation.isVisible() ? (await navigation.boundingBox()).y : viewport.height;
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(bottom + 1);
  // A geometrically visible control must also remain above fixed overlays.
  expect(await locator.evaluate((element) => {
    const r = element.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && (element === hit || element.contains(hit));
  })).toBe(true);
}

async function layoutTogether(page, editedControl) {
  const preview = page.locator('[data-avatar-preview]').getByRole('group', { name: 'Character view' });
  const save = page.getByRole('button', { name: 'Save avatar', exact: true });
  const label = editedControl.locator('..').locator('label');
  for (const element of [preview, label, editedControl, save]) await clearOfShell(page, element);
  const previewBounds = await preview.boundingBox();
  const controlBounds = await editedControl.boundingBox();
  const saveBounds = await save.boundingBox();
  const overlaps = (left, right) => Math.min(left.x + left.width, right.x + right.width) - Math.max(left.x, right.x) > 1
    && Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y) > 1;
  expect(overlaps(previewBounds, controlBounds)).toBe(false);
  expect(overlaps(previewBounds, saveBounds)).toBe(false);
  expect(overlaps(controlBounds, saveBounds)).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

for (const viewport of [{ width: 320, height: 568 }, { width: 375, height: 667 }, { width: 667, height: 375 }, { width: 1280, height: 800 }]) {
  test(`preview, edited wardrobe and Save fit together at ${viewport.width}×${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const state = await openEditor(page);
    const headwear = page.getByRole('combobox', { name: 'Headwear', exact: true });
    await headwear.locator('..').scrollIntoViewIfNeeded();
    await chooseDropdown(headwear, 'crown-eve');
    await layoutTogether(page, headwear);
    const quiver = page.getByRole('combobox', { name: 'Back accessory', exact: true });
    await quiver.locator('..').scrollIntoViewIfNeeded();
    await chooseDropdown(quiver, 'quiver-tale');
    await layoutTogether(page, quiver);
    await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeEnabled();
    expect(state.mutations).toEqual([]);
    await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeDisabled();
    expect(state.saved().accessories).toEqual(expect.objectContaining({ headwear: 'crown-eve', back: 'quiver-tale' }));
    expect(state.mutations).toEqual([{ path: '/api/character/avatar/configuration/', method: 'POST', body: { avatar_configuration: state.saved() } }]);
  });
}

test('drafts update live, Undo restores saved choices, failed saves retain edits and Profile shows confirmed appearance', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  const state = await openEditor(page);
  const headwear = page.getByRole('combobox', { name: 'Headwear', exact: true });
  await chooseDropdown(headwear, 'crown-eve');
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeEnabled();
  expect(state.mutations).toEqual([]);
  await page.getByRole('button', { name: 'Undo changes', exact: true }).click();
  await expect(headwear).toHaveJSProperty('value', 'none');
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeDisabled();
  await chooseDropdown(headwear, 'hood-mystical');
  state.failSave();
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.getByText('Synthetic save unavailable. Try again.')).toBeVisible();
  await expect(headwear).toHaveJSProperty('value', 'hood-mystical');
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeEnabled();
  await headwear.locator('..').scrollIntoViewIfNeeded();
  await layoutTogether(page, headwear);
  expect(state.saved().accessories.headwear).toBe('none');
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeDisabled();
  expect(state.saved().accessories.headwear).toBe('hood-mystical');
  await page.getByRole('button', { name: 'Back to Profile', exact: true }).click();
  await expect(page).toHaveURL(`${origin}/sigil`);
  await expect(page.getByRole('button', { name: 'Quick actions (clocked in)', exact: true })).toBeVisible();
  await page.goto(`${origin}/profile/customize`);
  await expect(page.getByRole('combobox', { name: 'Headwear', exact: true })).toHaveJSProperty('value', 'hood-mystical');
  expect(state.mutations).toHaveLength(2);
});

test('a future Knight retains shared bow/quiver IDs with a safe unavailable renderer', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  const state = await openEditor(page, { unavailableAdapter: true });
  await expect(page.getByRole('img', { name: 'Your Knight avatar' })).toBeVisible();
  const fallback = page.getByText('The avatar preview is unavailable. You can still customize your look.');
  await expect(fallback).toBeVisible();
  await clearOfShell(page, fallback);
  await expect(page.locator('[data-avatar-preview] canvas')).toHaveCount(0);
  expect(state.modelRequests).toEqual([]);
  const bow = page.getByRole('combobox', { name: 'Left hand', exact: true });
  await chooseDropdown(bow, 'bow-greenhorn');
  const quiver = page.getByRole('combobox', { name: 'Back accessory', exact: true });
  await chooseDropdown(quiver, 'quiver-rook');
  await expect(bow).toHaveJSProperty('value', 'bow-greenhorn');
  await expect(quiver).toHaveJSProperty('value', 'quiver-rook');
  await chooseDropdown(page.getByRole('combobox', { name: 'Right hand', exact: true }), 'synthetic-sword');
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeEnabled();
  await chooseDropdown(page.getByRole('combobox', { name: 'Avatar', exact: true }), 'female-archer');
  await expect(bow).toHaveJSProperty('value', 'bow-greenhorn');
  await expect(quiver).toHaveJSProperty('value', 'quiver-rook');
  await expect(page.getByRole('combobox', { name: 'Right hand', exact: true })).toHaveCount(0);
  await expect(page.getByText(/Synthetic sword/)).toBeVisible();
  await page.getByRole('button', { name: 'Save avatar', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeDisabled();
  expect(state.saved().accessories).toEqual(expect.objectContaining({ left_hand: 'bow-greenhorn', back: 'quiver-rook', right_hand: 'none' }));
  await chooseDropdown(page.getByRole('combobox', { name: 'Avatar', exact: true }), 'synthetic-knight');
  await expect(bow).toHaveJSProperty('value', 'bow-greenhorn');
  await expect(quiver).toHaveJSProperty('value', 'quiver-rook');
  await expect(page.getByRole('img', { name: 'Your Knight avatar' })).toBeVisible();
  await expect(page.locator('[data-avatar-preview] canvas')).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Right hand', exact: true })).toHaveJSProperty('value', 'none');
  expect(state.mutations).toEqual([{ path: '/api/character/avatar/configuration/', method: 'POST', body: { avatar_configuration: state.saved() } }]);
});

test('returning with unsaved changes preserves edits on Cancel and discards only on explicit confirmation', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  const state = await openEditor(page);
  const headwear = page.getByRole('combobox', { name: 'Headwear', exact: true });
  await chooseDropdown(headwear, 'crown-eve');
  await page.getByRole('button', { name: 'Back to Profile', exact: true }).click();
  const confirmation = page.getByRole('alertdialog', { name: 'Unsaved avatar changes' });
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(headwear).toHaveJSProperty('value', 'crown-eve');
  await expect(page.getByRole('button', { name: 'Save avatar', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Back to Profile', exact: true }).click();
  await confirmation.getByRole('button', { name: 'Discard and leave', exact: true }).click();
  await expect(page).toHaveURL(`${origin}/sigil`);
  await page.goto(`${origin}/profile/customize`);
  await expect(page.getByRole('combobox', { name: 'Headwear', exact: true })).toHaveJSProperty('value', 'none');
  expect(state.mutations).toEqual([]);
});

async function archerPixels(canvas, { minimumHeight = 0, details = false } = {}) {
  const bytes = await canvas.screenshot();
  const frame = PNG.sync.read(bytes);
  let colored = 0;
  let sampled = 0;
  let minX = frame.width;
  let minY = frame.height;
  let maxX = -1;
  let maxY = -1;
  // The middle column excludes the Reset overlay. Uniform sky cannot satisfy
  // either the visibility threshold or the actual silhouette size check.
  for (let y = 0; y < frame.height; y += 1) {
    for (let x = Math.floor(frame.width * 0.2); x < frame.width * 0.8; x += 1) {
      const offset = (y * frame.width + x) * 4;
      sampled += 1;
      if (skyRgb.some((value, channel) => Math.abs(frame.data[offset + channel] - value) > 12)) {
        colored += 1;
        minX = Math.min(minX, x); minY = Math.min(minY, y);
        maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
      }
    }
  }
  expect(colored / sampled, 'Actual Archer must visibly occupy the compact preview.').toBeGreaterThan(0.05);
  const bbox = { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
  expect(bbox.height, 'The actual Archer must be large enough to inspect choices.').toBeGreaterThanOrEqual(minimumHeight);
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  return details ? { sha256, model_bbox_pixels: bbox } : sha256;
}

test('existing private Archer follows wardrobe drafts and remains visible beside phone controls', async ({ page }) => {
  test.skip(!privateWardrobeArt, 'Optional private schema-v3 runtime art is absent; public fallback checks remain applicable.');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const state = await openEditor(page);
  if (captureDirectory) {
    expect(isAbsolute(captureDirectory), 'Private preview destination must be an explicit absolute path.').toBe(true);
    await mkdir(captureDirectory, { recursive: true, mode: 0o700 });
  }
  const captures = [];
  for (const viewport of [{ width: 320, height: 568 }, { width: 375, height: 667 }, { width: 667, height: 375 }, { width: 1280, height: 800 }]) {
    await page.setViewportSize(viewport);
    const headwear = page.getByRole('combobox', { name: 'Headwear', exact: true });
    await headwear.locator('..').scrollIntoViewIfNeeded();
    await chooseDropdown(headwear, 'none');
    const canvas = page.locator('[data-avatar-preview] canvas');
    await expect(page.locator('[data-avatar-preview]').getByRole('button', { name: 'Reset view', exact: true })).toBeEnabled();
    const bare = await archerPixels(canvas, { minimumHeight: 100 });
    await chooseDropdown(headwear, 'crown-eve');
    await expect(page.locator('[data-avatar-preview]').getByRole('button', { name: 'Reset view', exact: true })).toBeEnabled();
    expect(await archerPixels(canvas, { minimumHeight: 100 })).not.toBe(bare);
    await layoutTogether(page, headwear);
    const quiver = page.getByRole('combobox', { name: 'Back accessory', exact: true });
    await quiver.locator('..').scrollIntoViewIfNeeded();
    await chooseDropdown(quiver, 'quiver-tale');
    await expect(page.locator('[data-avatar-preview]').getByRole('button', { name: 'Reset view', exact: true })).toBeEnabled();
    const pixels = await archerPixels(canvas, { minimumHeight: 100, details: true });
    await layoutTogether(page, quiver);
    if (captureDirectory) {
      const file = `wardrobe-${viewport.width}x${viewport.height}.png`;
      await page.mouse.move(1, 1);
      const bytes = await page.screenshot({ path: join(captureDirectory, file) });
      captures.push({ viewport, file, sha256: createHash('sha256').update(bytes).digest('hex'),
        model_bbox_pixels: pixels.model_bbox_pixels,
        preview: await page.locator('[data-avatar-preview]').getByRole('group', { name: 'Character view' }).boundingBox(),
        edited_control: await quiver.boundingBox(), save: await page.getByRole('button', { name: 'Save avatar', exact: true }).boundingBox() });
    }
  }
  expect(state.mutations).toEqual([]);
  if (captureDirectory) await writeFile(join(captureDirectory, 'browser-evidence.json'), JSON.stringify({
    schema_version: 1, recorded_at: new Date().toISOString(), local_synthetic_api: true,
    unchanged_existing_runtime: true, physical_phone_acceptance: false, mutations: state.mutations, captures,
  }, null, 2) + '\n');
});
