import { test, expect } from '@playwright/test';
import { chooseDropdown, dropdownListbox } from './dropdown-helpers.js';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { createHash } from 'node:crypto';
import playwrightUtils from 'playwright-core/lib/utilsBundle';

const root = fileURLToPath(new URL('..', import.meta.url));
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find(entry => entry.family_id === 'meshtint-pedestal-card-ui');
const manifestPath = pin && new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url);
const manifest = manifestPath && existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, 'utf8')) : null;
const screenshotDirectory = process.env.ABBY_PRIVATE_ACCEPTANCE_DIR;
if (screenshotDirectory && (!isAbsolute(screenshotDirectory) || !relative(resolve(root, '..'), resolve(screenshotDirectory)).startsWith('..'))) {
  throw new Error('ABBY_PRIVATE_ACCEPTANCE_DIR must be an absolute private directory outside the checkout.');
}
let server, origin;
const { PNG } = playwrightUtils;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

// Paid artwork must never enter Playwright's hosted trace/video/screenshot
// attachments. Local screenshots require an explicit external private path.
test.use({
  trace: 'off', video: 'off', screenshot: 'off',
  launchOptions: async ({ browserName }, provideOptions) => {
    await provideOptions(browserName === 'chromium' ? { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } : {});
  },
});
test.beforeAll(async () => {
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: root,
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolveOrigin, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Pedestal acceptance server startup timed out.')), 30_000);
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Acceptance server exited ${code}.`)); });
    server.stdout.on('data', chunk => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolveOrigin(match[0]); }
    });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

async function open(page, mode = '') {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.goto(`${origin}/e2e/pedestal-card-ui-fixture.html${mode ? `?mode=${mode}` : ''}`);
  return errors;
}

async function privateCapture(page, name) {
  if (!screenshotDirectory) return;
  mkdirSync(screenshotDirectory, { recursive: true, mode: 0o700 });
  await page.screenshot({ path: resolve(screenshotDirectory, `${name}.png`), fullPage: true });
}

async function renderedCanvas(canvas) {
  const bytes = await canvas.screenshot();
  const frame = PNG.sync.read(bytes);
  const colors = new Set();
  for (let y = Math.floor(frame.height * 0.15); y < frame.height * 0.9; y += 3) {
    for (let x = Math.floor(frame.width * 0.15); x < frame.width * 0.85; x += 3) {
      const index = (y * frame.width + x) * 4;
      colors.add(`${frame.data[index] >> 4},${frame.data[index + 1] >> 4},${frame.data[index + 2] >> 4}`);
    }
  }
  expect(colors.size, 'Actual native meshes must visibly occupy the canvas.').toBeGreaterThan(30);
  return sha(bytes);
}

test('missing private assets preserve the surrounding application controls', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  const errors = await open(page, 'fallback');
  await expect(page.getByText('The decorative 3D display is unavailable.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing hatch controls' })).toBeEnabled();
  await expect(page.locator('canvas')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('current showcase controls and measured frame content reflow at phone and desktop widths', async ({ page }) => {
  const errors = await open(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['hyrule', 'vigil']) {
    await chooseDropdown(page.getByRole('combobox', { name: 'Color theme', exact: true }), theme);
    for (const width of [320, 375, 1280]) {
      await page.setViewportSize({ width, height: 740 });
      await expect(page.getByRole('combobox', { name: 'Egg artwork', exact: true })).toBeVisible();
      await page.getByRole('checkbox', { name: 'Long content', exact: true }).check();
      await page.getByRole('checkbox', { name: 'Larger text', exact: true }).check();
      const frame = page.locator('[data-pedestal-frame]');
      const content = page.locator('[data-pedestal-frame-content]');
      await frame.scrollIntoViewIfNeeded();
      const bounds = await frame.boundingBox();
      const opening = await content.boundingBox();
      expect(bounds.width / bounds.height).toBeCloseTo(1, 2);
      expect((opening.x - bounds.x) / bounds.width).toBeCloseTo(0.166015625, 2);
      expect((opening.y - bounds.y) / bounds.height).toBeCloseTo(0.181640625, 2);
      expect(opening.width / bounds.width).toBeCloseTo(0.666015625, 2);
      expect(opening.height / bounds.height).toBeCloseTo(0.638671875, 2);
      expect(await content.evaluate(element => getComputedStyle(element).overflowY)).toBe('auto');
      expect(await content.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      await content.evaluate(element => { element.scrollTop = element.scrollHeight; });
      expect(await content.evaluate(element => element.scrollTop + element.clientHeight >= element.scrollHeight - 1)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await privateCapture(page, `layout-${theme}-${width}`);
    }
  }
  expect(errors).toEqual([]);
});

test('all six GLBs render on their native rigs and all four loops move the actual scene', async ({ page }) => {
  test.skip(!manifest, 'Private immutable payload absent; actual GLB rendering acceptance remains pending.');
  await page.setViewportSize({ width: 375, height: 812 });
  const errors = await open(page);
  const canvas = page.locator('[data-pedestal-scene-selection] canvas');
  const preview = page.locator('[data-display-state]');
  const loaded = new Set();
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('.glb') && !url.searchParams.has('import')) loaded.add(url.pathname.split('/').at(-1));
  });
  for (const assetId of ['', 'normal-egg', 'legendary-egg', 'legendary-egg-idle-breath', 'legendary-egg-idle-wobble', 'legendary-egg-hatching-soon']) {
    await chooseDropdown(page.getByRole('combobox', { name: 'Egg artwork', exact: true }), assetId);
    await preview.scrollIntoViewIfNeeded();
    await expect(preview).toHaveAttribute('data-display-state', 'ready');
    await expect(canvas).toBeVisible();
    const first = await renderedCanvas(canvas);
    if (assetId === '' || /idle-breath|idle-wobble|hatching-soon/.test(assetId)) {
      await expect.poll(() => renderedCanvas(canvas), { intervals: [100, 200, 400], message: 'Native AnimationMixer playback must change rendered pixels.' }).not.toBe(first);
    }
    await privateCapture(page, `native-${assetId || 'plant-loop'}`);
  }
  for (const asset of manifest.assets.filter(asset => asset.kind !== 'image')) {
    expect([...loaded].some(filename => filename.startsWith(asset.variants[0].file.split('/').at(-1).slice(0, 32))), `Loaded native model ${asset.id}`).toBe(true);
  }
  expect(errors).toEqual([]);
});

test('actual posed vertices stay finite and clear the transformed support and surrounding pedestal throughout every loop', async ({ page }) => {
  test.skip(!manifest, 'Private immutable payload absent; complete native motion clearance remains pending.');
  test.setTimeout(300_000);
  await open(page, 'probe');
  await page.getByRole('button', { name: 'Inspect current native playback' }).click();
  const output = page.locator('[data-native-probe-result]');
  await expect(output).toHaveAttribute('data-native-probe-result', 'complete', { timeout: 260_000 });
  const result = JSON.parse(await output.textContent());
  if (screenshotDirectory) {
    mkdirSync(screenshotDirectory, { recursive: true, mode: 0o700 });
    writeFileSync(resolve(screenshotDirectory, 'native-motion-clearance.json'), JSON.stringify(result, null, 2), { mode: 0o600 });
  }
  expect(result.error).toBeUndefined();
  expect(result.manifestSha256).toBe(pin.manifest_sha256);
  expect(result.entries).toHaveLength(6);
  for (const entry of result.entries) {
    expect(entry.allFinite, entry.assetId).toBe(true);
    expect(entry.skinnedMeshes, entry.assetId).toBeGreaterThan(0);
    expect(entry.vertices, entry.assetId).toBeGreaterThan(100);
    expect(entry.samples, entry.assetId).toBeGreaterThanOrEqual(301);
    expect(entry.rootScale, entry.assetId).toEqual([0.37, 0.37, 0.37]);
    expect(entry.worldAnchor[0]).toBeCloseTo(1.2, 8);
    expect(entry.worldAnchor[1]).toBeCloseTo(-0.3 + 2.028465509414673 * 0.37, 8);
    expect(entry.worldAnchor[2]).toBeCloseTo(0.5, 8);
    if (entry.assetId !== 'trunk-pedestal') {
      expect(Number.isFinite(entry.minimumClearance), entry.assetId).toBe(true);
      expect(Number.isFinite(entry.minimumSurroundingClearance), entry.assetId).toBe(true);
      expect(entry.maximumEggRadius, 'Every posed egg vertex remains within the measured one-metre support disk.').toBeLessThan(1);
      expect(entry.worldPlacement[1] - entry.worldAnchor[1]).toBeCloseTo(0.002 * 0.37, 8);
      expect(entry.minimumClearance, entry.assetId).toBeGreaterThanOrEqual(0.001);
      expect(entry.minimumSurroundingClearance, entry.assetId).toBeGreaterThanOrEqual(0.001);
      expect(entry.initialHeight, 'Authored metre scale is preserved.').toBeGreaterThan(0.9);
      expect(entry.initialHeight).toBeLessThan(1.5);
    }
    if (!['normal-egg', 'legendary-egg'].includes(entry.assetId)) expect(entry.maxDisplacement, `${entry.assetId} native skin actually moves`).toBeGreaterThan(0.001);
  }
});

test('all 19 image assets and 35 variants preserve proportional complete PNG canvases', async ({ page }) => {
  test.skip(!manifest, 'Private immutable payload absent; actual PNG layout acceptance remains pending.');
  const errors = await open(page, 'images');
  const images = page.locator('[data-pedestal-image]');
  await expect(images).toHaveCount(35);
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded();
    await expect(image).toHaveAttribute('data-image-state', 'ready');
    const img = image.locator('img');
    const dimensions = await img.evaluate(element => ({
      width: element.naturalWidth, height: element.naturalHeight,
      renderedWidth: element.getBoundingClientRect().width, renderedHeight: element.getBoundingClientRect().height,
      objectFit: getComputedStyle(element).objectFit, rendering: getComputedStyle(element).imageRendering,
    }));
    const native = await image.getAttribute('data-image-variant') === 'native';
    expect(dimensions.width).toBe(native ? 1024 : 512);
    expect(dimensions.height).toBe(dimensions.width);
    expect(dimensions.renderedWidth / dimensions.renderedHeight).toBeCloseTo(1, 2);
    expect(dimensions.objectFit).toBe('contain');
    expect(dimensions.rendering).toBe('auto');
  }
  expect(new Set(await images.evaluateAll(nodes => nodes.map(node => node.dataset.pedestalImage))).size).toBe(19);
  await privateCapture(page, 'all-image-variants');
  expect(errors).toEqual([]);
});

test('corrupt native bytes and image failures retain fallbacks; retry and reduced motion recover safely', async ({ page }) => {
  test.skip(!manifest, 'Private immutable payload absent; real transport recovery acceptance remains pending.');
  const errors = await open(page);
  const preview = page.locator('[data-display-state]');
  const canvas = page.locator('[data-pedestal-scene-selection] canvas');
  await canvas.scrollIntoViewIfNeeded();
  await expect(preview).toHaveAttribute('data-display-state', 'ready');
  const selected = manifest.assets.find(asset => asset.id === 'legendary-egg-idle-wobble').variants[0].file.split('/').at(-1);
  await page.route(`**/${selected}*`, route => route.fulfill({ contentType: 'model/gltf-binary', body: 'corrupt-private-model' }));
  await chooseDropdown(page.getByRole('combobox', { name: 'Egg artwork', exact: true }), 'legendary-egg-idle-wobble');
  await expect(preview).toHaveAttribute('data-display-state', 'unavailable');
  await expect(page.getByRole('combobox', { name: 'Egg artwork', exact: true })).toBeEnabled();
  await page.unroute(`**/${selected}*`);
  await page.getByRole('button', { name: 'Retry 3D display' }).click();
  await canvas.scrollIntoViewIfNeeded();
  await expect(preview).toHaveAttribute('data-display-state', 'ready');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.getByText('Animations are paused.', { exact: true })).toBeVisible();
  let previous, stable = 0;
  await expect.poll(async () => {
    const current = await renderedCanvas(canvas);
    stable = current === previous ? stable + 1 : 0;
    previous = current;
    return stable;
  }, { intervals: [100, 200, 300] }).toBeGreaterThanOrEqual(2);
  await canvas.evaluate(element => element.getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
  await expect(preview).toHaveAttribute('data-display-state', 'unavailable');
  await page.getByRole('button', { name: 'Retry 3D display' }).click();
  await expect(preview).toHaveAttribute('data-display-state', 'ready');
  const png = manifest.assets.find(asset => asset.id === 'card-front-fire').variants.find(variant => variant.id === 'web').file.split('/').at(-1);
  await page.route(`**/${png}*`, route => route.abort());
  await chooseDropdown(page.getByRole('combobox', { name: 'UI artwork', exact: true }), 'card-front-fire');
  const image = page.locator('[data-pedestal-image="card-front-fire"]');
  await image.scrollIntoViewIfNeeded();
  await expect(image).toHaveAttribute('data-image-state', 'error');
  await expect(image.getByRole('img', { name: 'Card Front Fire' })).toBeVisible();
  await page.unroute(`**/${png}*`);
  await chooseDropdown(page.getByRole('combobox', { name: 'UI artwork', exact: true }), 'card-front-ice');
  await chooseDropdown(page.getByRole('combobox', { name: 'UI artwork', exact: true }), 'card-front-fire');
  await expect(image).toHaveAttribute('data-image-state', 'ready');
  expect(errors).toEqual([]);
});

test('the Hatchery keeps approved inventory, timed incubation and explicit server-confirmed hatching', async ({ page }) => {
  const writes = [];
  let incubation = null;
  let ready = false;
  const waiting = { id: 7, egg: { name: 'Chick Egg', icon: '🥚' }, potion: { name: 'Base Potion' }, remaining_seconds: 7200, is_ready: false, status: 'incubating' };
  const serverNow = '2026-10-18T10:00:00Z';
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith('/api/')) return route.continue();
    if (request.method() !== 'GET') writes.push({ path, method: request.method(), body: request.postDataJSON() });
    if (path === '/api/pets/incubations/' && request.method() === 'POST') {
      incubation = waiting;
      return route.fulfill({ status: 201, json: { incubation, server_now: serverNow } });
    }
    if (path === '/api/pets/incubations/7/hatch/' && request.method() === 'POST') {
      incubation = null;
      return route.fulfill({ status: 201, json: {
        incubation: { ...waiting, status: 'hatched', pet_id: 99 }, freshly_hatched: true, server_now: serverNow,
        pet: { id: 99, species: { name: 'Chick', icon: '🐤' }, potion: { name: 'Base', slug: 'base' } },
      } });
    }
    const bodies = {
      '/api/pets/stable/': { pets: [], mounts: [], total_possible: 1 },
      '/api/pets/incubations/': { incubation: incubation && { ...incubation, is_ready: ready, remaining_seconds: ready ? 0 : 7200, status: ready ? 'ready' : 'incubating' }, duration_seconds: 7200, server_now: serverNow },
      '/api/inventory/': [
        { id: 1, quantity: 1, item: { id: 11, name: 'Chick Egg', icon: '🥚', item_type: 'egg', catalog_available: true } },
        { id: 2, quantity: 1, item: { id: 22, name: 'Base Potion', icon: '🧪', item_type: 'potion', catalog_available: true } },
        { id: 3, quantity: 1, item: { id: 33, name: 'Earlier Egg', item_type: 'egg', catalog_available: false } },
      ],
      '/api/sprites/catalog/': {},
    };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(bodies[path] ?? []) });
  });
  // Install the network fence before API interception (newer routes run first).
  await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.fallback() : route.abort());
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${origin}/e2e/pedestal-card-ui-fixture.html?mode=hatchery`);
  await expect(page.getByRole('combobox', { name: 'Egg', exact: true })).toBeVisible();
  const eggPicker = page.getByRole('combobox', { name: 'Egg', exact: true });
  await eggPicker.click();
  await expect(dropdownListbox(eggPicker).getByRole('option', { name: /Earlier Egg/ })).toHaveCount(0);
  await expect(dropdownListbox(eggPicker).getByRole('option', { name: /Chick Egg/ })).toBeVisible();
  await eggPicker.press('Escape');
  await chooseDropdown(eggPicker, '11');
  await chooseDropdown(page.getByRole('combobox', { name: 'Potion', exact: true }), '22');
  expect(writes).toEqual([]);
  if (manifest) {
    await page.locator('canvas').scrollIntoViewIfNeeded();
    await expect(page.locator('[data-display-state]')).toHaveAttribute('data-display-state', 'ready');
    await privateCapture(page, 'hatchery-phone');
    await page.getByRole('button', { name: 'Turn off 3D display' }).click();
    await expect(page.getByText('3D display is off.')).toBeVisible();
    expect(writes).toEqual([]);
  }
  await expect(page.getByRole('button', { name: 'Hatch pet', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Start incubation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your egg is incubating' })).toBeVisible();
  await expect(page.getByText('Ready to hatch in 2h.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Hatch pet', exact: true })).toHaveCount(0);
  expect(writes).toEqual([{ path: '/api/pets/incubations/', method: 'POST', body: { egg_item_id: '11', potion_item_id: '22', request_id: expect.stringMatching(/^[\da-f-]{36}$/i) } }]);
  ready = true;
  await page.getByRole('button', { name: 'Check readiness' }).click();
  await page.getByRole('button', { name: 'Hatch pet', exact: true }).click();
  await expect(page.getByRole('alertdialog')).toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual({ path: '/api/pets/incubations/7/hatch/', method: 'POST', body: null });
});
