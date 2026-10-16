import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const birdPin = lock.releases.find((entry) => entry.family_id === 'meshtint-bird-evolution');
const sharedPath = birdPin && new URL(`../src/avatar/shared/${birdPin.directory}/manifest.json`, import.meta.url);
const sharedBird = sharedPath && existsSync(sharedPath) ? JSON.parse(readFileSync(sharedPath, 'utf8')) : null;
const privateArt = !!sharedBird || existsSync(fileURLToPath(new URL('../src/companion/licensed/manifest.json', import.meta.url)));
test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });
test.beforeAll(async () => {
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  origin = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Vite fixture startup timed out: ${output}`)), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    devServer.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});
test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

test('unsupported species retain exact 2D presentation and phone-accessible controls', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto(`${origin}/e2e/companion-fixture.html`);
  await page.getByRole('button', { name: 'Use Fox', exact: true }).click();
  await expect(page.getByRole('img', { name: 'Base Fox' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Show 3D view' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Say hello' }).click();
  await expect(page.getByText(/hello, base fox/i)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing care controls' })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('licensed GLBs render and preserve controls across context loss, retry and stage change', async ({ page }, testInfo) => {
  test.skip(!privateArt, 'No private licensed exports; asset acceptance remains incomplete.');
  const failures = [];
  const warnings = [];
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error' || message.type() === 'warning') warnings.push(message.text()); });
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto(`${origin}/e2e/companion-fixture.html`);
  await page.getByRole('button', { name: 'Show 3D view' }).click();
  await expect(page.locator('canvas')).toBeVisible().catch((error) => { throw new Error(`${error.message}\n${JSON.stringify({ failures, warnings })}`); });
  await expect(page.getByText('Loading the woodland…')).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Animate companion' }).check();
  await page.getByRole('button', { name: 'Say hello' }).click();
  await page.screenshot({ path: testInfo.outputPath('chick-phone.png'), fullPage: true });
  await page.evaluate(() => {
    const gl = document.querySelector('canvas').getContext('webgl2');
    const loss = gl.getExtension('WEBGL_lose_context');
    if (!loss) throw new Error('The test browser cannot exercise WebGL context loss.');
    loss.loseContext();
  });
  await expect(page.getByText(/3d view could not load/i)).toBeVisible();
  await expect(page.getByRole('img', { name: 'Base Chick' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing care controls' })).toBeEnabled();
  await page.getByRole('button', { name: 'Retry 3D view' }).click();
  await expect(page.locator('canvas')).toBeVisible();
  await expect(page.getByText('Loading the woodland…')).toHaveCount(0);
  await page.getByRole('button', { name: 'Use evolved Bird' }).click();
  await expect(page.getByText('Evolved companion · Active')).toBeVisible();
  await expect(page.locator('canvas')).toBeVisible();
  await expect(page.getByText('Loading the woodland…')).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Animate companion' }).check();
  await page.screenshot({ path: testInfo.outputPath('bird-phone.png'), fullPage: true });
  await page.getByRole('button', { name: 'Use 2D view' }).click();
  await expect(page.locator('canvas')).toHaveCount(0);
  expect(failures, JSON.stringify(warnings)).toEqual([]);
});

test('a failed licensed download falls back and can retry without changing ownership or controls', async ({ page }) => {
  test.skip(!privateArt, 'No private licensed exports; asset failure/recovery remains incomplete.');
  const chick = sharedBird?.assets.find((entry) => entry.id === 'chick');
  const idle = chick?.variants.find((entry) => entry.id === chick.default_variant);
  const modelUrl = idle ? `**/src/avatar/shared/${birdPin.directory}/${idle.file}` : '**/src/companion/licensed/chick.glb';
  await page.route(modelUrl, (route) => route.abort('failed'));
  await page.goto(`${origin}/e2e/companion-fixture.html`);
  await page.getByRole('button', { name: 'Show 3D view' }).click();
  await expect(page.getByText(/3d view could not load/i)).toBeVisible();
  await expect(page.getByRole('img', { name: 'Base Chick' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing care controls' })).toBeEnabled();
  await expect(page.getByText('35/100 growth · Active')).toBeVisible();
  await page.unroute(modelUrl);
  await page.getByRole('button', { name: 'Retry 3D view' }).click();
  await expect(page.locator('canvas')).toBeVisible();
  await expect(page.getByText('Loading the woodland…')).toHaveCount(0);
  await expect(page.getByText(/3d view could not load/i)).toHaveCount(0);
});
