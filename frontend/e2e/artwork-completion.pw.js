import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { access, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers';

test.use({ trace: 'off', video: 'off', screenshot: 'off' });
const frontend = fileURLToPath(new URL('..', import.meta.url));
const evidence = process.env.ABBY_ARTWORK_EVIDENCE_DIR;
let installed = true;
try { await access(`${frontend}/src/avatar/shared/abby-artwork-completion`); } catch { installed = false; }
test.skip(!installed, 'Private artwork import is required; public CI validates labelled fallbacks.');
let server;
let origin;

test.beforeAll(async () => {
  server = spawn(process.execPath, [`${frontend}/node_modules/vite/bin/vite.js`, '--host', '127.0.0.1', '--port', '0'], {
    cwd: frontend, stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|HOME|SYSTEMROOT|TEMP|TMP)$/i.test(key))),
  });
  let output = '';
  origin = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Vite startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited ${code}`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
  if (evidence) await mkdir(evidence, { recursive: true });
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const stopped = once(server, 'exit'); server.kill(); await stopped;
  }
});

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort('blockedbyclient');
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json: {} });
    return route.continue();
  });
});

for (const theme of ['hyrule', 'vigil']) {
  test(`all 365 illustrations decode with production components on ${theme}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1024, height: 1000 });
    await page.goto(`${origin}/e2e/artwork-completion-fixture.html?theme=${theme}`);
    const groupPicker = page.getByRole('combobox', { name: 'Artwork group' });
    await chooseDropdown(page.getByRole('combobox', { name: 'Artwork size' }), '64');
    const urls = new Set();
    for (const [key, label, count] of [['badges', 'Badges', 182], ['categories', 'Categories', 14], ['subjects', 'Subjects', 34], ['skills', 'Skills', 96], ['items', 'Items and accessories', 33], ['challenges', 'Challenges', 5], ['birthday', 'Birthday', 1]]) {
      await chooseDropdown(groupPicker, key);
      const group = page.getByRole('group', { name: `${label} artwork`, exact: true });
      const images = group.locator('img[data-artwork-image]');
      await expect(images).toHaveCount(count);
      await images.evaluateAll((elements) => elements.forEach((element) => { element.loading = 'eager'; }));
      await expect.poll(() => images.evaluateAll((elements) => elements.filter((element) => element.complete && element.naturalWidth === 256 && element.naturalHeight === 256).length)).toBe(count);
      const rendered = await images.evaluateAll((elements) => elements.map((element) => ({
        url: element.src, width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height,
        rendering: getComputedStyle(element).imageRendering, alt: element.alt,
      })));
      for (const image of rendered) {
        expect(image).toMatchObject({ width: 64, height: 64, rendering: 'auto', alt: '' });
        urls.add(image.url);
      }
      if (evidence) {
        // Bounded sheets keep every illustration legible when inspected.
        const figures = group.locator('figure');
        for (let start = 0; start < count; start += 48) {
          await figures.evaluateAll((elements, offset) => elements.forEach((element, index) => { element.style.display = index < offset || index >= offset + 48 ? 'none' : ''; }), start);
          await group.screenshot({ path: `${evidence}/${theme}-${key}-${start}.png` });
        }
        await figures.evaluateAll((elements) => elements.forEach((element) => { element.style.display = ''; }));
      }
    }
    expect(urls.size).toBe(365);
    for (const size of [24, 32, 40, 64, 96]) {
      await chooseDropdown(page.getByRole('combobox', { name: 'Artwork size' }), String(size));
      const image = page.getByRole('group', { name: 'Birthday artwork', exact: true }).locator('img');
      expect(await image.evaluate((element) => ({ width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height }))).toEqual({ width: size, height: size });
    }
    const production = page.getByRole('region', { name: 'Production components' });
    await production.scrollIntoViewIfNeeded();
    await expect(production.locator('[data-artwork-image="badge-10-hour-club"]')).toHaveCount(3);
    await expect(production.getByText('CUSTOM BADGE', { exact: true })).toBeVisible();
    await expect(production.getByText('CUSTOM', { exact: true })).toBeVisible();
    for (const id of ['category-coding', 'subject-coding-languages-apps', 'skill-coding-python']) {
      const image = production.locator(`[data-artwork-image="${id}"]`);
      await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth)).toBe(256);
    }
    for (const name of ['Crown (saved only)', 'Watermelon Slice', 'Birthday Week']) {
      await expect.poll(() => production.getByRole('img', { name, exact: true }).evaluate((element) => element.complete && element.naturalWidth)).toBe(256);
    }
    if (evidence) await production.screenshot({ path: `${evidence}/${theme}-production.png` });
    await production.getByRole('button', { name: '10-Hour Club · common', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '10-Hour Club' });
    await expect(dialog.locator('[data-artwork-image="badge-10-hour-club"]')).toBeVisible();
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await production.getByRole('button', { name: 'Show birthday example' }).click();
    const birthday = page.getByRole('alertdialog', { name: 'Happy birthday' });
    const candle = birthday.locator('[data-artwork-image="birthday-candle"]');
    await expect.poll(() => candle.evaluate((element) => element.naturalWidth)).toBe(256);
    expect((await candle.boundingBox()).width).toBe(64);
    await expect(birthday.getByText('15', { exact: true })).toBeVisible();
    await expect(birthday.getByText(/125 coins added/)).toBeVisible();
    await expect(birthday.locator('.relative').first()).toHaveCSS('opacity', '1');
    if (evidence) await page.screenshot({ path: `${evidence}/${theme}-birthday.png` });
    await birthday.getByRole('button', { name: 'Turn the page →' }).click();
    await expect(birthday).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test('failed images preserve full authored glyphs and birthday placeholder', async ({ page }) => {
  await page.route('**/abby-artwork-completion/**/objects/*.png*', (route) => route.request().resourceType() === 'image'
    ? route.fulfill({ status: 404, body: '' }) : route.fallback());
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${origin}/e2e/artwork-completion-fixture.html`);
  const production = page.getByRole('region', { name: 'Production components' });
  await production.locator('img').evaluateAll((elements) => elements.forEach((element) => { element.loading = 'eager'; }));
  await expect(production.locator('[data-artwork-image]')).toHaveCount(0);
  await expect(production.getByText('TEN', { exact: true })).toHaveCount(3);
  for (const glyph of ['CODE', 'APPS', 'PYTHON']) await expect(production.getByText(glyph, { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await production.getByRole('button', { name: 'Show birthday example' }).click();
  const birthday = page.getByRole('alertdialog');
  const placeholder = birthday.locator('img');
  await expect(placeholder).toHaveCount(1);
  await expect.poll(() => placeholder.evaluate((element) => element.complete && element.naturalWidth)).toBe(64);
  await expect(placeholder).toHaveAttribute('alt', '');
  if (evidence) await page.screenshot({ path: `${evidence}/failed-images-mobile.png` });
});
