import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;

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

for (const theme of ['hyrule', 'vigil']) {
  for (const width of [320, 375, 768, 1280]) {
    test(`collection navigation fits ${width}px on ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 740 });
      await page.goto(`${origin}/e2e/design-gallery-fixture.html?theme=${theme}`);
      for (const name of ['Demo badge collections', 'Demo Guide topics', 'Demo Inventory filters']) {
        const picker = page.getByRole('tablist', { name });
        await expect(picker).toBeVisible();
        await expect(picker.getByRole('tab', { selected: true })).toHaveCount(1);
        await expect(picker.locator('[tabindex="0"]')).toHaveCount(1);
        for (const tab of await picker.getByRole('tab').all()) {
          const bounds = await tab.boundingBox();
          expect(bounds.height).toBeGreaterThanOrEqual(44);
          expect(bounds.x).toBeGreaterThanOrEqual(0);
          expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
          expect(await tab.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
        }
      }
      const filters = page.getByRole('tablist', { name: 'Demo Inventory filters' });
      const tabs = filters.getByRole('tab');
      // Test selection without scrolling after the complete row is visible.
      // WebKit can focus an offscreen control without revealing it immediately.
      await filters.scrollIntoViewIfNeeded();
      await tabs.first().focus();
      const initialScroll = await page.evaluate(() => window.scrollY);
      await page.keyboard.press('End');
      await expect(tabs.last()).toBeFocused();
      await expect(tabs.last()).toHaveAttribute('aria-selected', 'true');
      expect(await page.evaluate(() => window.scrollY)).toBe(initialScroll);
      await page.keyboard.press('ArrowRight');
      await expect(tabs.first()).toBeFocused();
      await expect(tabs.first()).toHaveAttribute('aria-selected', 'true');
      await page.keyboard.press('Home');
      await expect(tabs.first()).toBeFocused();
      expect(await page.evaluate(() => window.scrollY)).toBe(initialScroll);
    });
  }
}

test('keyboard navigation reveals a collection on a short phone screen', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 260 });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  const tabs = page.getByRole('tablist', { name: 'Demo badge collections' }).getByRole('tab');
  await tabs.first().focus();
  await expect(tabs.first()).toBeFocused();
  await expect(tabs.last()).not.toBeInViewport({ ratio: 1 });
  await page.keyboard.press('End');
  await expect(tabs.last()).toBeFocused();
  await expect(tabs.last()).toBeInViewport({ ratio: 1 });
  await expect(tabs.last()).toHaveAttribute('aria-selected', 'true');
});

test('Wayfinder demo follows a cross-category requirement without API requests', async ({ page }) => {
  const apiRequests = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  const demo = page.getByRole('region', { name: 'Skills · Wayfinder' });
  await demo.getByRole('button', { name: /^Woodworking,/ }).click();
  await demo.getByRole('button', { name: /^Finishing & decorative techniques,/ }).click();
  await demo.getByRole('button', { name: /Inlay Work/ }).click();
  await expect(demo.getByRole('heading', { name: 'Inlay Work', exact: true })).toBeVisible();
  await demo.getByRole('button', { name: /Gilding/ }).click();
  await expect(demo.getByRole('heading', { name: 'Gilding', exact: true })).toBeVisible();
  await demo.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(demo.getByRole('heading', { name: 'Inlay Work', exact: true })).toBeVisible();
  expect(apiRequests).toEqual([]);
});

test('keyboard reveal clears the sticky header and mobile navigation', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html?shell=1`);
  const tabs = page.getByRole('tablist', { name: 'Demo badge collections' }).getByRole('tab');
  const header = page.locator('[data-journal-sticky-header]');
  const navigation = page.locator('[data-journal-bottom-nav]');

  // A target can be inside the viewport while its top is covered by the header.
  await tabs.first().evaluate((element) => {
    window.scrollTo(0, window.scrollY + element.getBoundingClientRect().top - 30);
    element.focus({ preventScroll: true });
  });
  await page.keyboard.press('Home');
  await expect(tabs.first()).toBeFocused();
  expect((await tabs.first().boundingBox()).y).toBeGreaterThanOrEqual((await header.boundingBox()).height);

  // Likewise, a lower row can be covered by the fixed navigation bar.
  await tabs.last().evaluate((element) => {
    window.scrollTo(0, window.scrollY + element.getBoundingClientRect().bottom - (window.innerHeight - 30));
    element.focus({ preventScroll: true });
  });
  await page.keyboard.press('End');
  await expect(tabs.last()).toBeFocused();
  const bounds = await tabs.last().boundingBox();
  expect(bounds.y + bounds.height).toBeLessThanOrEqual((await navigation.boundingBox()).y);
});

test('design library previews covers and recovers a failed read without API requests', async ({ page }) => {
  const apiRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());
  });
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  await page.getByRole('combobox', { name: 'Color theme', exact: true }).selectOption('vigil');
  await expect.poll(() => page.evaluate(() => document.documentElement.style.getPropertyValue('--color-ink-page'))).toBe('#292538');
  const states = page.getByRole('region', { name: 'Data and feedback', exact: true });
  await states.getByRole('combobox', { name: 'Data state', exact: true }).selectOption('error');
  await expect(states.getByRole('alert')).toContainText('Could not load activities');
  await expect(states.getByText('No activities yet', { exact: true })).toHaveCount(0);
  await states.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(states.getByText('Make a paper kite', { exact: true })).toBeVisible();
  await states.getByRole('combobox', { name: 'Data state', exact: true }).selectOption('filtered');
  await states.getByRole('button', { name: 'Clear filter', exact: true }).click();
  await expect(states.getByText('Make a paper kite', { exact: true })).toBeVisible();
  expect(apiRequests).toEqual([]);
});

test('design library preserves a dirty form and returns focus after saving', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  await page.getByRole('checkbox', { name: 'Larger text', exact: true }).check();
  const opener = page.getByRole('button', { name: 'Open example form', exact: true });
  await opener.click();
  const dialog = page.getByRole('dialog', { name: 'Edit activity', exact: true });
  await expect(dialog.getByRole('textbox', { name: 'Activity name', exact: true })).toHaveCSS('font-size', '22px');
  await dialog.getByRole('textbox', { name: 'Activity name', exact: true }).fill('Build a kite');
  await page.keyboard.press('Escape');
  const confirmation = page.getByRole('alertdialog');
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog.getByRole('textbox', { name: 'Activity name', exact: true })).toHaveValue('Build a kite');
  await dialog.getByRole('button', { name: 'Save example', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('Example saved: Build a kite', { exact: true })).toBeVisible();
  await expect(opener).toBeFocused();
  await page.getByRole('checkbox', { name: 'Larger text', exact: true }).uncheck();
  expect(await page.evaluate(() => document.body.style.getPropertyValue('--text-base'))).toBe('');
});

test('design library retains an attachment after failure and removes it locally', async ({ page }) => {
  const writes = [];
  page.on('request', request => {
    if (['POST', 'PATCH', 'DELETE'].includes(request.method())) writes.push(request.url());
  });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  const attachments = page.getByRole('region', { name: 'Attachments', exact: true });
  await attachments.getByLabel('Example photo', { exact: true }).setInputFiles({
    name: 'synthetic-photo.png', mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/eioAAAAASUVORK5CYII=', 'base64'),
  });
  await expect(attachments.getByText('synthetic-photo.png', { exact: true })).toBeVisible();
  await attachments.getByRole('button', { name: 'Preview upload failure', exact: true }).click();
  await expect(attachments.getByRole('alert')).toContainText('selected file is still available');
  await expect(attachments.getByText('synthetic-photo.png', { exact: true })).toBeVisible();
  await attachments.getByRole('button', { name: 'Remove example photo', exact: true }).click();
  await expect(attachments.getByText('No file selected', { exact: true })).toBeVisible();
  await expect(attachments.getByRole('alert')).toHaveCount(0);
  expect(writes).toEqual([]);
});

for (const theme of ['hyrule', 'vigil', 'sunlit', 'snowquill', 'verdant', 'harvest']) {
  test(`design library enlarged content reflows on a real phone viewport on ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(`${origin}/e2e/design-gallery-fixture.html?theme=${theme}`);
    await page.getByRole('checkbox', { name: 'Long content', exact: true }).check();
    await page.getByRole('checkbox', { name: 'Larger text', exact: true }).check();
    await page.getByRole('combobox', { name: 'Example role', exact: true }).selectOption('parent');
    await expect(page.getByRole('combobox', { name: 'Viewing', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    const notification = page.getByRole('group', { name: 'success notification example', exact: true });
    await notification.getByRole('button', { name: 'Dismiss notification', exact: true }).click();
    await expect(notification).toHaveCount(0);
    await page.getByRole('button', { name: 'Restore notification examples', exact: true }).click();
    await expect(notification).toBeVisible();
  });
}
