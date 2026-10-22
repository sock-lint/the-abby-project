import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFileSync, existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { isAbsolute, join } from 'node:path';
import { stripVTControlCharacters } from 'node:util';

// Licensed PNGs and their screenshots must not enter public test artifacts.
test.use({ trace: 'off', video: 'off', screenshot: 'off' });
const frontend = fileURLToPath(new URL('..', import.meta.url));
const checkout = fileURLToPath(new URL('../..', import.meta.url));
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find((entry) => entry.family_id === 'abby-portrait-frame-kit');
const manifestPath = pin && `${frontend}/src/avatar/shared/${pin.directory}/manifest.json`;
const imported = !!manifestPath && existsSync(manifestPath);
const manifest = imported ? JSON.parse(readFileSync(manifestPath, 'utf8')) : null;
test.skip(!imported, 'Private portrait kit import is required; the ordinary identity suite covers public SVG fallbacks.');
const families = ['laurel', 'steampunk', 'rune-circle', 'cosmic', 'scholar', 'pixel'];
const evidence = process.env.ABBY_PORTRAIT_EVIDENCE_DIR;
let server;
let origin;

test.beforeAll(async () => {
  expect(pin.release_version).toBe('1.1.0');
  expect(pin.manifest_sha256).toBe('9c2e4e3c67edc2fa639bd8d92ff27d5929c356b220ccd4868dd2a3550c25bb91');
  server = spawn(process.execPath, [`${frontend}/node_modules/vite/bin/vite.js`, '--host', '127.0.0.1', '--port', '0'], {
    cwd: frontend, stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|HOME|SYSTEMROOT|WINDIR|TEMP|TMP|USERPROFILE)$/i.test(key))),
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Portrait fixture startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Portrait fixture exited ${code}: ${output}`)); });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
  if (evidence) {
    if (!isAbsolute(evidence) || evidence.startsWith(checkout)) throw new Error('Portrait evidence requires an absolute directory outside the checkout.');
    await mkdir(evidence, { recursive: true });
  }
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const stopped = once(server, 'exit');
    server.kill();
    await stopped;
  }
});

let unexpectedRequests;
test.beforeEach(async ({ page }) => {
  unexpectedRequests = [];
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpectedRequests.push({ method: request.method(), path: url.pathname });
      return route.abort();
    }
    if (url.pathname === '/synthetic/unavailable-picture.png') return route.fulfill({ status: 404, body: '' });
    return route.continue();
  });
});

function selectedVariant(family, size, dpr) {
  const variantId = `${size < 64 ? 'small' : 'detail'}-${size}-${dpr}x`;
  return manifest.assets.find((asset) => asset.id === `item-frame-${family}`).variants.find((variant) => variant.id === variantId);
}

for (const dpr of [1, 2, 3]) {
  test.describe(`${dpr}x density`, () => {
    test.use({ deviceScaleFactor: dpr });
    for (const theme of ['hyrule', 'vigil']) {
      test(`six frame families preserve pictures and initials at all four accepted sizes on ${theme}`, async ({ page }, info) => {
        const errors = [];
        page.on('pageerror', (error) => errors.push(error.message));
        await page.setViewportSize({ width: 1024, height: 850 });
        await page.goto(`${origin}/e2e/portrait-frame-kit-fixture.html?theme=${theme}`);
        for (const size of [32, 40, 64, 96]) {
          const section = page.getByRole('region', { name: `${size}px portraits`, exact: true });
          const overlays = section.locator('[data-portrait-overlay]');
          await expect(overlays).toHaveCount(12);
          await expect.poll(() => overlays.evaluateAll((images) => images.filter((image) => image.complete && image.naturalWidth > 0).length)).toBe(12);
          const sources = new Set();
          for (const family of families) {
            const figure = section.locator(`[data-kit-example="frame-${family}"]`);
            const expected = selectedVariant(family, size, dpr);
            for (const kind of ['initial', 'photo']) {
              const portrait = figure.locator(`[data-picture-kind="${kind}"] [data-portrait-frame]`);
              const overlay = portrait.locator(`[data-portrait-overlay="item-frame-${family}"]`);
              await portrait.scrollIntoViewIfNeeded();
              await expect(overlay).toBeVisible();
              await expect(overlay).toHaveAttribute('data-portrait-variant', expected.id);
              await expect(overlay).toHaveAttribute('alt', '');
              await expect(overlay).toHaveAttribute('aria-hidden', 'true');
              const actual = await overlay.evaluate((image) => ({ src: image.currentSrc, width: image.naturalWidth, height: image.naturalHeight,
                renderedWidth: image.getBoundingClientRect().width, renderedHeight: image.getBoundingClientRect().height,
                pointerEvents: getComputedStyle(image).pointerEvents, rendering: getComputedStyle(image).imageRendering }));
              expect(new URL(actual.src).pathname.endsWith(`/${expected.file}`)).toBe(true);
              expect(actual).toMatchObject({ width: size * dpr, height: size * dpr, renderedWidth: size, renderedHeight: size,
                pointerEvents: 'none', rendering: 'auto' });
              sources.add(actual.src);
              await expect(portrait.locator('[data-portrait-ornament]')).toHaveCount(0);
              const geometry = await portrait.evaluate((element) => {
                const outer = element.getBoundingClientRect();
                const underlay = element.querySelector('.profile-portrait__image');
                const inner = underlay.getBoundingClientRect();
                return { width: outer.width, height: outer.height, left: inner.left - outer.left, top: inner.top - outer.top,
                  innerWidth: inner.width, innerHeight: inner.height, overflow: getComputedStyle(element).overflow,
                  clip: getComputedStyle(underlay).borderRadius };
              });
              expect(geometry).toMatchObject({ width: size, height: size, overflow: 'visible', clip: '50%' });
              expect(geometry.left).toBeCloseTo(size * 180 / 1024, 1);
              expect(geometry.top).toBeCloseTo(size * 180 / 1024, 1);
              expect(geometry.innerWidth).toBeCloseTo(size * 664 / 1024, 1);
              expect(geometry.innerHeight).toBeCloseTo(size * 664 / 1024, 1);
              const clearOpening = await overlay.evaluate((image) => {
                const canvas = document.createElement('canvas');
                canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
                const context = canvas.getContext('2d');
                context.drawImage(image, 0, 0);
                return [[0.5, 0.5], [0.3, 0.5], [0.7, 0.5], [0.5, 0.3], [0.5, 0.7]].map(([x, y]) =>
                  context.getImageData(Math.floor(x * canvas.width), Math.floor(y * canvas.height), 1, 1).data[3]);
              });
              expect(clearOpening).toEqual([0, 0, 0, 0, 0]);
              if (kind === 'initial') await expect(portrait.locator('.profile-portrait__initial')).toHaveText('A');
              else {
                const picture = portrait.locator('.profile-portrait__image img');
                await expect.poll(() => picture.evaluate((image) => image.complete && image.naturalWidth)).toBe(512);
                await expect(picture).toHaveCSS('object-fit', 'cover');
                await expect(picture).toHaveCSS('object-position', '50% 50%');
              }
            }
          }
          expect(sources.size).toBe(6);
          if (evidence && dpr === 1) await section.screenshot({ path: join(evidence, `${info.project.name || 'chromium'}-${theme}-${size}px.png`) });
        }
        const unreviewed = page.getByRole('region', { name: 'Unreviewed canvas sizes', exact: true });
        await expect(unreviewed.locator('[data-portrait-overlay]')).toHaveCount(0);
        await expect(unreviewed.locator('[data-portrait-ornament]')).toHaveCount(3);
        expect(unexpectedRequests).toEqual([]);
        expect(errors).toEqual([]);
      });
    }
  });
}

test('pictures and initials retain all six identities on the remaining Meadow covers', async ({ page }, info) => {
  await page.setViewportSize({ width: 1024, height: 850 });
  for (const theme of ['sunlit', 'snowquill', 'verdant', 'harvest']) {
    await page.goto(`${origin}/e2e/portrait-frame-kit-fixture.html?theme=${theme}`);
    const section = page.getByRole('region', { name: '64px portraits', exact: true });
    const overlays = section.locator('[data-portrait-overlay]');
    await expect(overlays).toHaveCount(12);
    await expect.poll(() => overlays.evaluateAll((images) => images.filter((image) => image.complete && image.naturalWidth === 64).length)).toBe(12);
    await expect(section.locator('[data-picture-kind="initial"] .profile-portrait__initial')).toHaveCount(6);
    await expect(section.locator('.profile-portrait__image img')).toHaveCount(6);
    for (const family of families) await expect(section.locator(`[data-kit-example="frame-${family}"] [data-portrait-overlay]`)).toHaveCount(2);
    if (evidence) await section.screenshot({ path: join(evidence, `${info.project.name || 'chromium'}-${theme}-64px.png`) });
  }
  expect(unexpectedRequests).toEqual([]);
});

test('failed selected PNGs retain the same frame identity and recover with a new density URL', async ({ page }) => {
  const failed = selectedVariant('laurel', 32, 1);
  await page.route(`**/${failed.file}*`, (route) => route.request().resourceType() === 'image'
    ? route.fulfill({ status: 404, body: '' }) : route.fallback());
  await page.goto(`${origin}/e2e/portrait-frame-kit-fixture.html`);
  const section = page.getByRole('region', { name: '32px portraits', exact: true });
  const frame = section.locator('[data-kit-example="frame-laurel"]');
  for (const kind of ['initial', 'photo']) {
    const portrait = frame.locator(`[data-picture-kind="${kind}"] [data-portrait-frame="laurel"]`);
    await expect(portrait.locator('[data-portrait-ornament]')).toBeVisible();
    await expect(portrait.locator('[data-portrait-overlay]')).not.toBeVisible();
  }
  await expect(frame.locator('[data-picture-kind="initial"] .profile-portrait__initial')).toHaveText('A');
  await expect.poll(() => frame.locator('[data-picture-kind="photo"] .profile-portrait__image img').evaluate((image) => image.complete && image.naturalWidth)).toBe(512);
  await page.getByRole('button', { name: 'Use alternate density', exact: true }).click();
  const restored = frame.locator('[data-portrait-overlay="item-frame-laurel"]');
  await expect.poll(() => restored.evaluateAll((images) => images.filter((image) => image.complete && image.naturalWidth === 64).length)).toBe(2);
  await expect(frame.locator('[data-portrait-ornament]')).toHaveCount(0);
  expect(unexpectedRequests).toEqual([]);
});

test('failed pictures retain initials under the selected artwork and recover on replacement', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  await page.goto(`${origin}/e2e/portrait-frame-kit-fixture.html`);
  await page.getByRole('button', { name: 'Use unavailable picture', exact: true }).click();
  const section = page.getByRole('region', { name: '64px portraits', exact: true });
  await expect(section.locator('[data-picture-kind="photo"] .profile-portrait__initial')).toHaveCount(6);
  await expect(section.locator('[data-portrait-overlay]')).toHaveCount(12);
  await page.getByRole('button', { name: 'Restore picture', exact: true }).click();
  const pictures = section.locator('.profile-portrait__image img');
  await expect.poll(() => pictures.evaluateAll((images) => images.filter((image) => image.complete && image.naturalWidth === 512).length)).toBe(6);
  for (const button of await page.getByRole('button').all()) {
    const bounds = await button.boundingBox();
    expect(bounds.width).toBeGreaterThanOrEqual(44);
    expect(bounds.height).toBeGreaterThanOrEqual(44);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(unexpectedRequests).toEqual([]);
});
