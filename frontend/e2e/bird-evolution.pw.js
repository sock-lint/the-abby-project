import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';
import { stripVTControlCharacters } from 'node:util';

const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find((entry) => entry.family_id === 'meshtint-bird-evolution');
const manifestPath = pin && new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url);
const manifest = manifestPath && existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, 'utf8')) : null;
let server, origin;
const playback = (page) => page.getByRole('status', { name: 'Companion playback' });
test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });
test.beforeAll(async () => {
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Bird fixture startup timed out.')), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Bird fixture exited ${code}.`)); });
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
async function open(page) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  // Synthetic local ownership only. No traffic may reach a production service.
  await page.route('**/*', (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto(`${origin}/e2e/companion-fixture.html`);
  await page.getByRole('button', { name: 'Show 3D view' }).click();
  await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
  await page.getByRole('checkbox', { name: 'Animate companion' }).check();
  return errors;
}

test('all 31 published motions render on native rigs; both confirmed evolutions settle into destination idle', async ({ page }, info) => {
  test.skip(!manifest, 'Private shared Bird payload absent; real asset acceptance remains pending.');
  const errors = await open(page);
  let count = 0;
  const modelRequests = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('.glb') && !url.searchParams.has('import')) modelRequests.push(url.pathname);
  });
  for (const stage of ['chick', 'fledgling', 'bird']) {
    if (stage !== 'chick') {
      await page.getByRole('button', { name: stage === 'bird' ? 'Use evolved Bird' : 'Use Fledgling', exact: true }).click();
      await expect(playback(page)).toHaveAttribute('data-playback-status', 'evolving');
      await page.screenshot({ path: info.outputPath(`evolve-to-${stage}.png`), fullPage: true });
      await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
      await expect(playback(page)).toHaveAttribute('data-stage', stage);
      await expect(playback(page)).toHaveAttribute('data-variant-id', 'source-idle');
    }
    await page.screenshot({ path: info.outputPath(`${stage}-idle.png`), fullPage: true });
    const loaded = modelRequests.length;
    await page.getByRole('button', { name: 'Reload saved companion', exact: true }).click();
    await page.waitForLoadState('networkidle');
    await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
    expect(modelRequests.length, 'A same-stage saved-state reload must retain the native rig and consumed evolution.').toBe(loaded);
    await page.getByText('More motions', { exact: true }).click();
    const variants = manifest.assets.find((entry) => entry.id === stage).variants;
    await expect(page.getByRole('combobox', { name: 'Companion motion' }).locator('option')).toHaveCount(variants.length);
    for (const variant of variants) {
      await page.getByRole('combobox', { name: 'Companion motion' }).selectOption(variant.id);
      await page.getByRole('button', { name: 'Play motion', exact: true }).click();
      // Offscreen scenes pause; returning to the canvas must retain the request.
      await page.locator('canvas').scrollIntoViewIfNeeded();
      await expect(playback(page)).toHaveAttribute('data-variant-id', variant.id);
      const clip = variant.animations.clips[0];
      if (clip.loop) {
        await expect(playback(page)).toHaveAttribute('data-playback-status', variant.id === 'source-idle' ? 'idle' : 'playing');
      } else {
        await expect(playback(page)).toHaveAttribute('data-playback-status', 'playing');
        await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
      }
      await page.getByRole('button', { name: 'Return to rest', exact: true }).click();
      await page.locator('canvas').scrollIntoViewIfNeeded();
      await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
      count += 1;
    }
  }
  expect(count).toBe(31);
  expect(errors).toEqual([]);
  await expect(page.getByRole('button', { name: 'Existing care controls' })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('interrupted loads, stage replacement, retry and reduced motion keep the confirmed destination', async ({ page }) => {
  test.skip(!manifest, 'Private shared Bird payload absent; lifecycle acceptance remains pending.');
  const errors = await open(page);
  const fledgling = manifest.assets.find((entry) => entry.id === 'fledgling');
  const idle = fledgling.variants.find((entry) => entry.id === fledgling.default_variant);
  const routePattern = `**/${idle.file}`;
  await page.route(routePattern, (route) => route.abort('failed'));
  await page.getByRole('button', { name: 'Use Fledgling', exact: true }).click();
  await expect(page.getByText(/3d view could not load/i)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing care controls' })).toBeEnabled();
  await page.unroute(routePattern);
  await page.getByRole('button', { name: 'Retry 3D view', exact: true }).click();
  await expect(playback(page)).toHaveAttribute('data-stage', 'fledgling');
  await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Use evolved Bird', exact: true }).click();
  await expect(playback(page)).toHaveAttribute('data-stage', 'bird');
  await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
  await page.getByRole('button', { name: 'Use Fox', exact: true }).click();
  await expect(playback(page)).toHaveCount(0);
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Base Fox' })).toBeVisible();
  // The intentional load error is caught by the optional scene boundary.
  expect(errors.filter((message) => !/fetch|load|GLB|Failed/i.test(message))).toEqual([]);
});
