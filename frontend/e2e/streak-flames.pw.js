import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { captureFlameEvidence, flameStages, imageDocumentMetadata, privateFlames } from './streak-flame-helpers.js';

// Authored SVG source and private previews stay out of public failure artifacts.
test.use({ trace: 'off', video: 'off', screenshot: 'off' });
let server;
let origin;

test.beforeAll(async () => {
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|HOME|SYSTEMROOT|WINDIR|TEMP|TMP|USERPROFILE)$/i.test(key))),
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Flame fixture startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Flame fixture exited ${code}: ${output}`)); });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const stopped = once(server, 'exit');
    server.kill();
    await stopped;
  }
});

let unexpected;
test.beforeEach(async ({ page }) => {
  unexpected = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpected.push({ method: route.request().method(), path: url.pathname });
      return route.abort();
    }
    return route.continue();
  });
});
test.afterEach(() => expect(unexpected).toEqual([]));

test('unknown bonus remains a neutral placeholder separate from the dormant stage', async ({ page }) => {
  await page.goto(`${origin}/e2e/flame-stages-fixture.html`);
  const unknown = page.getByRole('region', { name: 'Unknown bonus' }).locator('[data-header-streak-flame]');
  await expect(unknown).toHaveAttribute('data-state', 'unknown');
  await expect(unknown).toHaveAttribute('data-artwork-status', 'unavailable');
  await expect(unknown.locator('img')).toHaveCount(0);
  await expect(unknown.locator('.lucide-circle-question-mark')).toBeVisible();
  await expect(page.locator('[data-flame-example="dormant-ember"]')).toHaveCount(2);
});

test('an absent private family shows explicit unavailable placeholders without substitute artwork', async ({ page }) => {
  test.skip(Boolean(privateFlames), 'This case verifies the public checkout without the private family.');
  await page.goto(`${origin}/e2e/flame-stages-fixture.html`);
  const grid = page.locator('[data-flame-grid]');
  await expect(grid.locator('img')).toHaveCount(0);
  await expect(grid.locator('[data-artwork-status="unavailable"]')).toHaveCount(16);
  await expect(grid.locator('.lucide-circle-question-mark')).toHaveCount(16);
  for (const stage of flameStages) await expect(grid.locator(`[data-state="${stage}"]`)).toHaveCount(4);
});

for (const theme of ['hyrule', 'vigil']) {
  for (const grayscale of [false, true]) {
    test(`exact private flames retain their full canvases at 20/24px on ${theme}${grayscale ? ' in grayscale' : ''}`, async ({ page }, info) => {
      test.skip(!privateFlames, 'Exact active, imported private flame family is required; public fallback checks remain active.');
      await page.setViewportSize({ width: 960, height: 520 });
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.goto(`${origin}/e2e/flame-stages-fixture.html?theme=${theme}&grayscale=${grayscale ? 1 : 0}`);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('main')).toHaveCSS('background-color', theme === 'hyrule' ? 'rgb(255, 248, 238)' : 'rgb(41, 37, 56)');
      const grid = page.locator('[data-flame-grid]');
      await expect(grid).toHaveCSS('filter', grayscale ? 'grayscale(1)' : 'none');
      await expect(grid.locator('img')).toHaveCount(16);
      await expect(grid.locator('linearGradient')).toHaveCount(0);
      for (const size of [20, 24]) {
        const baselines = [];
        const silhouettes = [];
        for (const stage of flameStages) {
          const row = grid.locator(`[data-flame-example="${stage}"][data-flame-size="${size}"]`);
          await expect(row).toHaveAttribute('data-release-family', privateFlames.pin.family_id);
          await expect(row).toHaveAttribute('data-release-version', privateFlames.pin.release_version);
          await expect(row).toHaveAttribute('data-release-manifest', privateFlames.pin.manifest_sha256);
          await expect(row).toHaveAttribute('data-release-sha256', privateFlames.stages[stage].sha256);
          const images = row.locator('img');
          for (const image of await images.all()) {
            expect(await imageDocumentMetadata(image)).toEqual({
              width: '24', height: '24', viewBox: '0 0 24 24', naturalWidth: 24, naturalHeight: 24,
              idCount: 1, uniqueIdCount: 1, activeElements: 0, sha256: privateFlames.stages[stage].sha256,
            });
            const box = await image.boundingBox();
            expect(box.width).toBe(size);
            expect(box.height).toBe(size);
            await expect(image).toHaveCSS('clip-path', 'none');
            await expect(image).toHaveCSS('transform', 'none');
          }
          const pixels = await images.first().evaluate(async (node, { size, grayscale }) => {
            const canvas = document.createElement('canvas'); canvas.width = size; canvas.height = size;
            const context = canvas.getContext('2d');
            context.filter = grayscale ? 'grayscale(1)' : 'none';
            context.drawImage(node, 0, 0, size, size);
            const rgba = context.getImageData(0, 0, size, size).data;
            let left = size, top = size, right = -1, bottom = -1;
            for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
              if (rgba[(y * size + x) * 4 + 3] > 16) {
                left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
              }
            }
            const digest = await crypto.subtle.digest('SHA-256', rgba);
            return { left, top, right, bottom, digest: [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('') };
          }, { size, grayscale });
          // Transparent edge pixels preserve spark clearance; all four body
          // silhouettes retain the same authored baseline without normalization.
          expect(pixels.left).toBeGreaterThanOrEqual(1);
          expect(pixels.top).toBeGreaterThanOrEqual(1);
          expect(pixels.right).toBeLessThan(size - 1);
          expect(pixels.bottom).toBeLessThan(size - 1);
          baselines.push(pixels.bottom);
          silhouettes.push(pixels.digest);
        }
        expect(new Set(baselines).size).toBe(1);
        expect(new Set(silhouettes).size).toBe(4);
      }
      for (const preference of ['no-preference', 'reduce']) {
        await page.emulateMedia({ reducedMotion: preference });
        expect(await grid.locator('[data-header-streak-flame], img').evaluateAll((nodes) => nodes.every((node) => {
          const style = getComputedStyle(node);
          return style.animationName === 'none' && style.transform === 'none' && node.getAnimations().length === 0;
        }))).toBe(true);
      }
      await captureFlameEvidence(page, info, `flames-${theme}-${grayscale ? 'grayscale' : 'color'}.png`, { fullPage: true });
    });
  }
}
