import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { contrastRatio } from '../src/utils/contrast.js';

let devServer;
let origin;
test.beforeAll(async () => {
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Fixture startup timed out: ${output}`)), 30_000);
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

// Inspect the actual rendered foreground and composite every gradient stop
// over its ancestor surface. White text on a translucent pale tint otherwise
// passes an isolated token check while failing in the application.
async function renderedContrasts(locator, options = {}) {
  return locator.evaluate((element, options) => {
    const ctx = document.createElement('canvas').getContext('2d');
    const rgba = (value) => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = value;
      ctx.fillRect(0, 0, 1, 1);
      return [...ctx.getImageData(0, 0, 1, 1).data].map((v, i) => i === 3 ? v / 255 : v);
    };
    const blend = (fg, bg) => fg.slice(0, 3).map((v, i) => Math.round(v * fg[3] + bg[i] * (1 - fg[3])));
    const hex = (rgb) => '#' + rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
    const ancestry = [];
    for (let node = element; node; node = node.parentElement) ancestry.unshift(node);
    let surfaces = [[255, 255, 255]];
    let adjacent = surfaces;
    for (const node of ancestry) {
      if (node === element) adjacent = [...surfaces];
      const style = getComputedStyle(node);
      const background = rgba(style.backgroundColor);
      surfaces = surfaces.map((surface) => blend(background, surface));
      const stops = style.backgroundImage.match(/(?:rgba?|color|oklab|oklch|lab|lch|hsla?)\([^)]+\)/g);
      if (style.backgroundImage !== 'none' && !stops) throw new Error(`Uninspected surface: ${style.backgroundImage}`);
      if (stops) surfaces = surfaces.flatMap((surface) => stops.map((stop) => blend(rgba(stop), surface)));
    }
    const style = getComputedStyle(element, options.pseudo || null);
    if (options.pseudo) surfaces = surfaces.map((surface) => blend(rgba(style.backgroundColor), surface));
    const focusColor = style.boxShadow === 'none' ? style.outlineColor : style.getPropertyValue('--tw-ring-color');
    const foreground = rgba(options.focus ? focusColor : style[options.property || 'color']);
    if (options.adjacent) surfaces.push(...adjacent);
    return surfaces.map((surface) => ({ foreground: hex(blend(foreground, surface)), background: hex(surface) }));
  }, options);
}

for (const theme of ['hyrule', 'vigil', 'sunlit', 'snowquill', 'verdant', 'harvest']) {
  test(`control boundaries and focus contrast on ${theme}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(`${origin}/e2e/design-foundations-fixture.html?theme=${theme}`);
    for (const name of ['Example text', 'Example choice', 'Choice filter', 'Example date', 'From', 'Calendar sync']) {
      const control = page.getByLabel(name, { exact: true });
      for (const pair of await renderedContrasts(control, { property: 'borderTopColor', pseudo: name === 'Calendar sync' ? '::before' : null, adjacent: true })) {
        expect(contrastRatio(pair.foreground, pair.background), `${name} boundary on ${theme}`).toBeGreaterThanOrEqual(3);
      }
      await control.focus();
      const visibleFocus = await control.evaluate((node) => {
        const style = getComputedStyle(node);
        return style.boxShadow !== 'none' || (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2);
      });
      expect(visibleFocus, `${name} must show focus on ${theme}`).toBe(true);
      for (const pair of await renderedContrasts(control, { focus: true, adjacent: true })) {
        expect(contrastRatio(pair.foreground, pair.background), `${name} focus on ${theme}`).toBeGreaterThanOrEqual(3);
      }
    }
  });
  test(`readable feedback and deep-card text on ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(`${origin}/e2e/design-foundations-fixture.html?theme=${theme}`);
    await page.getByRole('button', { name: 'Show success', exact: true }).click();
    await page.getByRole('button', { name: 'Show general notification' }).click();
    for (const locator of [page.getByText('Secondary copy on a nested card'), page.getByText('Supporting caption on a nested card'), page.getByText('Your changes are saved'), page.getByText('A saved update'), page.getByText('Your changes are confirmed.')]) {
      for (const pair of await renderedContrasts(locator)) {
        expect(contrastRatio(pair.foreground, pair.background), `${await locator.textContent()} on ${theme}: ${JSON.stringify(pair)}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    const surfaces = page.getByRole('region', { name: 'Paired notification surfaces' });
    for (const copy of await surfaces.locator('.notification-surface > div > div').all()) {
      for (const pair of await renderedContrasts(copy)) expect(contrastRatio(pair.foreground, pair.background)).toBeGreaterThanOrEqual(4.5);
    }
    for (const dismiss of await surfaces.getByRole('button', { name: 'Dismiss notification' }).all()) {
      for (const pair of await renderedContrasts(dismiss)) expect(contrastRatio(pair.foreground, pair.background)).toBeGreaterThanOrEqual(4.5);
    }
    expect(await surfaces.locator('.notification-surface').evaluateAll((nodes) => nodes.every((node) => getComputedStyle(node).transform === 'none'))).toBe(true);
  });
}

test('form controls retain 44px hit areas on a short phone', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 360 });
  await page.goto(`${origin}/e2e/design-foundations-fixture.html`);
  for (const locator of [page.getByLabel('From'), page.locator('label').filter({ hasText: 'Share with my family' }), page.getByRole('switch', { name: 'Calendar sync' })]) {
    expect((await locator.boundingBox()).height).toBeGreaterThanOrEqual(44);
  }
  await page.getByText('Share with my family').click();
  await expect(page.getByRole('checkbox')).toBeChecked();
  await page.getByRole('switch').focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('switch')).not.toBeChecked();
});

test('changing motion preference preserves text being edited', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto(`${origin}/e2e/design-foundations-fixture.html`);
  const input = page.getByLabel('Example text', { exact: true });
  await input.fill('Keep this unfinished thought');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.getByTestId('page-reveal')).toHaveCSS('filter', 'none');
  await expect(input).toHaveValue('Keep this unfinished thought');
});

test('reduced motion settles pages, progress, loaders and nested sheets immediately', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 360 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/design-foundations-fixture.html`);
  await page.getByRole('button', { name: 'Replay page' }).click();
  const shell = page.getByTestId('page-reveal');
  await expect(shell).toHaveCSS('filter', 'none');
  await expect(shell).toHaveCSS('transform', 'none');
  const loader = page.getByRole('status', { name: 'Loading' });
  expect(await loader.locator('div').evaluateAll((nodes) => nodes.every((node) => getComputedStyle(node).animationName === 'none'))).toBe(true);
  const progress = page.getByRole('progressbar', { name: 'Saved progress' });
  expect(await progress.evaluate((node) => node.firstElementChild.getBoundingClientRect().width / node.getBoundingClientRect().width)).toBeCloseTo(0.75, 2);
  await page.getByRole('button', { name: 'Open form' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toHaveCSS('transform', 'none');
  await page.getByRole('textbox', { name: 'Your note' }).fill('Keep this draft');
  await page.keyboard.press('Escape');
  const confirm = page.getByRole('alertdialog');
  await expect(confirm).toHaveCSS('transform', 'none');
  await expect(confirm.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await confirm.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByRole('textbox', { name: 'Your note' })).toHaveValue('Keep this draft');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open form' })).toBeFocused();
});
