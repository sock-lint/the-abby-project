import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers.js';

const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find(({ family_id }) => family_id === 'abby-elemental-companions');
const manifestPath = pin && new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url);
const manifest = manifestPath && existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, 'utf8')) : null;
const stages = ['baby', 'middle', 'grown'];
const fullMotions = process.env.ABBY_ELEMENTAL_FULL_MOTIONS === '1';
let server, origin;
test.use({ viewport: { width: 390, height: 844 }, reducedMotion: 'no-preference',
  launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });
test.beforeAll(async () => {
  server = spawn(process.execPath, ['--input-type=module', '-e', "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: 0, hmr: false, watch: null } }); await server.listen(); server.printUrls();"], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timeout = setTimeout(() => reject(new Error('Elemental fixture startup timed out.')), 30_000);
    server.once('error', (error) => { clearTimeout(timeout); reject(error); });
    server.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Elemental fixture exited ${code}.`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const address = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (address) { clearTimeout(timeout); resolve(address[0]); }
    });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

async function open(page, species = 'chick', potion = 'fire') {
  const errors = [], mutations = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => { if (!['GET', 'HEAD'].includes(request.method())) mutations.push(request.method()); });
  // This fixture must never contact an application or publication service.
  await page.route('**/*', (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.goto(`${origin}/e2e/elemental-fixture.html`);
  await chooseDropdown(page.getByRole('combobox', { name: 'Fixture species' }), species);
  await chooseDropdown(page.getByRole('combobox', { name: 'Fixture potion' }), potion);
  await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-elemental-installed', 'true');
  return { errors, mutations };
}
const playback = (page) => page.getByRole('status', { name: 'Companion playback', exact: true });
async function resting(page, stage, name = 'Companion playback') {
  const status = page.getByRole('status', { name, exact: true });
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect(status).toHaveAttribute('data-playback-status', 'idle', { timeout: 45_000 });
  await expect(status).toHaveAttribute('data-stage', stage);
  await expect(status).toHaveAttribute('data-variant-id', 'source-idle');
}
async function observePlayback(page) {
  await playback(page).evaluate((element) => {
    window.__elementalObserver?.disconnect(); window.__elementalHistory = [];
    const record = () => window.__elementalHistory.push({ status: element.dataset.playbackStatus, variant: element.dataset.variantId, stage: element.dataset.stage });
    window.__elementalObserver = new MutationObserver(record);
    window.__elementalObserver.observe(element, { attributes: true }); record();
  });
}
async function play(page, binding) {
  const asset = manifest.assets.find(({ id }) => id === binding.asset_id), variant = asset.variants.find(({ id }) => id === binding.variant_id);
  const clip = variant.animations.clips.find(({ name }) => name === variant.animations.actions[binding.action]);
  await chooseDropdown(page.getByRole('combobox', { name: 'Companion motion' }), binding.variant_id);
  await observePlayback(page);
  await page.getByRole('button', { name: 'Play motion', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate((id) => window.__elementalHistory.some(({ variant }) => variant === id), binding.variant_id)).toBe(true);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  if (!clip.loop) await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
  await page.getByRole('button', { name: 'Return to rest', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
}

for (const species of ['chick', 'meshtint-wolf']) {
  for (const potion of ['fire', 'ice']) {
    test(`${species}/${potion}: actual owned and Hatchery forms, exact portraits and ${fullMotions ? 'all' : 'sampled'} native takes`, async ({ page }, info) => {
      test.setTimeout(fullMotions ? 600_000 : 240_000);
      test.skip(!manifest, 'Exact private elemental payloads absent; asset acceptance remains pending.');
      const { errors, mutations } = await open(page, species, potion);
      let rendered = 0;
      for (const stage of stages) {
        await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
        await resting(page, stage);
        await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-appearance-id', `${species}-${potion}-${stage}`);
        await page.screenshot({ path: info.outputPath(`${species}-${potion}-${stage}-live.png`), fullPage: true });
        await page.getByRole('button', { name: 'Reload saved companion', exact: true }).click();
        await resting(page, stage);
        await page.getByText('More motions', { exact: true }).click();
        const bindings = manifest.appearance_bindings.stages.filter((binding) => binding.species_slug === species && binding.potion_slug === potion && binding.lifecycle_stage === stage);
        const motions = fullMotions ? bindings : bindings.filter(({ motion }) => ['idle', 'turn-left'].includes(motion));
        for (const binding of motions) { await play(page, binding); rendered += 1; }
      }
      await chooseDropdown(page.getByRole('combobox', { name: 'Fixture surface' }), 'hatchery');
      const family = page.getByRole('region', { name: 'Family artwork preview' });
      await expect(family.getByRole('button', { name: 'Egg', exact: true })).toHaveAttribute('aria-pressed', 'true');
      for (const stage of stages) {
        await family.getByRole('button', { name: `${stage[0].toUpperCase()}${stage.slice(1)}`, exact: true }).click();
        const image = family.getByRole('img');
        await expect(image).toHaveAttribute('src', /\.png/);
        await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth === 256)).toBe(true);
        await page.getByRole('button', { name: 'Show 3D preview', exact: true }).click();
        await resting(page, stage, 'Family preview playback');
        await page.screenshot({ path: info.outputPath(`${species}-${potion}-${stage}-hatchery.png`), fullPage: true });
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.getByRole('button', { name: 'Unmount presentation', exact: true }).click();
      await expect(page.locator('canvas')).toHaveCount(0);
      expect(errors).toEqual([]); expect(mutations).toEqual([]);
      info.annotations.push({ type: 'native-takes-rendered', description: String(rendered) });
      info.annotations.push({ type: 'woodland', description: 'See fixture diagnostics: private populated Woodland is independently required.' });
    });
  }
}

test('all twelve portrait images and six catalog images use exact 256px art in a narrow layout', async ({ page }, info) => {
  test.skip(!manifest, 'Exact private elemental payloads absent; image acceptance remains pending.');
  const { errors, mutations } = await open(page);
  await chooseDropdown(page.getByRole('combobox', { name: 'Fixture surface' }), 'portraits');
  const gallery = page.getByRole('region', { name: 'Elemental portrait and catalog images' });
  await expect(gallery.locator('img')).toHaveCount(18);
  await expect.poll(() => gallery.locator('img').evaluateAll((images) => images.every((image) => image.complete && image.naturalWidth === 256))).toBe(true);
  for (const binding of manifest.appearance_bindings.stages.filter(({ motion }) => motion === 'idle')) {
    const portrait = manifest.assets.find(({ id }) => id === binding.portrait_asset_id).variants.find(({ id }) => id === binding.portrait_variant_id);
    await expect(gallery.getByTestId(`${binding.species_slug}-${binding.potion_slug}-${binding.lifecycle_stage}`).locator('img')).toHaveAttribute('src', new RegExp(portrait.file));
  }
  for (const id of ['item-fire-potion', 'item-ice-potion', 'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail']) {
    const image = manifest.assets.find((asset) => asset.id === id).variants.find(({ id: variantId }) => variantId === 'icon');
    await expect(gallery.getByTestId(id).locator('img')).toHaveAttribute('src', new RegExp(image.file));
  }
  expect(await gallery.locator('img').evaluateAll((images) => images.every((image) => !image.style.filter.includes('hue-rotate')))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('all-elemental-portraits-and-ui.png'), fullPage: true });
  expect(errors).toEqual([]); expect(mutations).toEqual([]);
});

for (const potion of ['fire', 'ice']) {
  test(`Chick/${potion}: both confirmed step transitions, direct jump and saved-state reload`, async ({ page }, info) => {
    test.skip(!manifest, 'Exact private elemental payloads absent; evolution acceptance remains pending.');
    const { errors, mutations } = await open(page, 'chick', potion);
    await resting(page, 'baby');
    const seen = [];
    page.on('request', (request) => { if (request.url().endsWith('.glb')) seen.push(request.url()); });
    for (const stage of ['middle', 'grown']) {
      await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
      await page.locator('canvas').scrollIntoViewIfNeeded();
      await expect(playback(page)).toHaveAttribute('data-playback-status', 'evolving');
      await page.screenshot({ path: info.outputPath(`chick-${potion}-evolving-${stage}.png`), fullPage: true });
      await resting(page, stage);
    }
    const beforeReload = seen.length;
    await page.getByRole('button', { name: 'Reload saved companion', exact: true }).click();
    await resting(page, 'grown'); expect(seen.length).toBe(beforeReload);
    await page.reload(); await resting(page, 'grown');
    await page.getByRole('button', { name: 'Set baby', exact: true }).click(); await resting(page, 'baby');
    const beforeJump = seen.length;
    await page.getByRole('button', { name: 'Set grown', exact: true }).click();
    await page.locator('canvas').scrollIntoViewIfNeeded();
    await expect(playback(page)).toHaveAttribute('data-playback-status', 'evolving');
    await resting(page, 'grown');
    const transitionFiles = manifest.appearance_bindings.transitions.filter((binding) => binding.species_slug === 'chick' && binding.potion_slug === potion)
      .map((binding) => manifest.assets.find(({ id }) => id === binding.asset_id).variants.find(({ id }) => id === binding.variant_id).file);
    for (const file of transitionFiles) expect(seen.slice(beforeJump).some((url) => url.endsWith(file)), `Direct jump must load the exact ${potion} ${file} transition.`).toBe(true);
    await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
    expect(errors).toEqual([]); expect(mutations).toEqual([]);
  });
}

test('reduced motion goes directly to the confirmed target; an unsupported identity keeps readable controls', async ({ page }, info) => {
  test.skip(!manifest, 'Exact private elemental payloads absent; reduced-motion acceptance remains pending.');
  const { errors, mutations } = await open(page);
  await resting(page, 'baby');
  const transitions = manifest.appearance_bindings.transitions.map((binding) => manifest.assets.find(({ id }) => id === binding.asset_id)
    .variants.find(({ id }) => id === binding.variant_id).file);
  const requests = [];
  page.on('request', (request) => { if (transitions.some((file) => request.url().endsWith(file))) requests.push(request.url()); });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Set grown', exact: true }).click(); await resting(page, 'grown');
  expect(requests).toEqual([]);
  await expect(page.getByRole('button', { name: 'Fly together', exact: true })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('reduced-motion-confirmed-bird.png'), fullPage: true });
  await page.getByRole('button', { name: 'Use unsupported identity', exact: true }).click();
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect(page.getByRole('img', { name: /Saved companion, your companion/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
  expect(errors).toEqual([]); expect(mutations).toEqual([]);
});

test('a failed exact model keeps its portrait and controls; retry loads the same confirmed appearance', async ({ page }, info) => {
  test.skip(!manifest, 'Exact private elemental payloads absent; load recovery acceptance remains pending.');
  const { errors, mutations } = await open(page, 'meshtint-wolf', 'ice');
  await resting(page, 'baby');
  const binding = manifest.appearance_bindings.stages.find((entry) => entry.species_slug === 'meshtint-wolf' && entry.potion_slug === 'ice' && entry.lifecycle_stage === 'middle' && entry.motion === 'idle');
  const variant = manifest.assets.find(({ id }) => id === binding.asset_id).variants.find(({ id }) => id === binding.variant_id);
  const pattern = `**/${variant.file}`;
  await page.route(pattern, (route) => route.abort('failed'));
  await page.getByRole('button', { name: 'Set middle', exact: true }).click();
  await expect(page.getByText('The 3D view could not load. Your companion and all controls are still available.')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Ice Wolf, your companion' })).toHaveAttribute('src', /\.png/);
  await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
  await page.screenshot({ path: info.outputPath('failed-exact-wolf-model.png'), fullPage: true });
  await page.unroute(pattern);
  await page.getByText('View', { exact: true }).click();
  await page.getByRole('button', { name: 'Retry 3D woodland', exact: true }).click();
  await resting(page, 'middle');
  expect(errors.filter((message) => !/fetch|load|GLB|Failed/i.test(message))).toEqual([]);
  expect(mutations).toEqual([]);
});
