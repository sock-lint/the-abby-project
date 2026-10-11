import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { readFile } from 'node:fs/promises';

let devServer;
let origin;

test.beforeAll(async () => {
  // A separate, local Vite process serves only synthetic UI fixtures. No
  // application credentials or running Django server are needed.
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

test.beforeEach(async ({ page }) => {
  await page.route('**/api/dashboard/**', async (route) => {
    if (new URL(route.request().url()).pathname !== '/api/dashboard/') return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ coin_balance: 1 }) });
  });
});

for (const width of [320, 375, 768, 1280]) {
  test(`shared controls fit a ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    await page.goto(`${origin}/e2e/mobile-ui-fixture.html`);
    const heading = page.getByRole('heading', { name: 'Family contribution approvals' });
    await expect(heading).toBeVisible();
    const versal = page.locator('[data-versal="true"]:visible');
    await expect(versal).toHaveCount(1);
    expect((await versal.boundingBox()).width).toBe(width < 640 ? 48 : 96);
    for (const control of [
      page.getByRole('button', { name: 'Review history' }),
      page.getByRole('button', { name: 'New contribution' }),
      page.getByRole('button', { name: 'Small icon action' }),
      page.getByRole('combobox', { name: 'Family member' }),
    ]) {
      const bounds = await control.boundingBox();
      expect(bounds.height).toBeGreaterThanOrEqual(44);
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    }
    const calendar = page.getByRole('button', { name: 'Add Project due: Building a rocket to calendar' });
    const calendarBounds = await calendar.boundingBox();
    expect(calendarBounds.height).toBeGreaterThanOrEqual(44);
    expect(calendarBounds.x + calendarBounds.width).toBeLessThanOrEqual(width);
    expect(await calendar.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    const select = page.getByRole('combobox', { name: 'Family member' });
    await select.selectOption({ label: 'Everyone' });
    await expect(select).toHaveValue('Everyone');
    await page.getByRole('button', { name: 'Open sheet' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet).toBeVisible();
    const close = sheet.getByRole('button', { name: 'Close', exact: true });
    await expect(close).toBeInViewport();
    const title = await sheet.getByRole('heading').boundingBox();
    const closeBounds = await close.boundingBox();
    expect(title.x + title.width).toBeLessThanOrEqual(closeBounds.x);
    await close.click();
    await expect(sheet).not.toBeVisible();
  });
}

test('confirmation actions remain reachable on a short phone screen', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 320 });
  await page.goto(`${origin}/e2e/mobile-ui-fixture.html`);
  await page.getByRole('button', { name: 'Open confirmation' }).click();
  const dialog = page.getByRole('alertdialog');
  const cancel = dialog.getByRole('button', { name: 'Cancel' });
  await expect(cancel).toBeFocused();
  await expect(cancel).toBeInViewport();
  const discard = dialog.getByRole('button', { name: 'Discard contribution changes' });
  await discard.scrollIntoViewIfNeeded();
  await expect(discard).toBeInViewport();
  const bounds = await dialog.boundingBox();
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(320);
  await discard.click();
  await expect(dialog).not.toBeVisible();
});

test('status scroll cues refresh after values grow and follow scroll and keyboard focus', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto(`${origin}/e2e/mobile-ui-fixture.html`);
  const shortcuts = page.getByRole('group', { name: 'Status shortcuts' });
  const rail = shortcuts.locator('.overflow-x-auto');
  await expect(shortcuts.getByRole('button', { name: '1 coins' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const originalWidth = (await rail.boundingBox()).width;
  await expect(shortcuts.locator('[data-scroll-fade]')).toHaveCount(0);

  await page.getByRole('button', { name: 'Grow status values' }).click();
  const coins = shortcuts.getByRole('button', { name: '123456789 coins' });
  await expect(coins).toBeVisible();
  expect((await rail.boundingBox()).width).toBe(originalWidth);
  await expect(shortcuts.locator('[data-scroll-fade="right"]')).toBeVisible();
  await expect(shortcuts.locator('[data-scroll-fade="left"]')).toHaveCount(0);

  await rail.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
  await expect(shortcuts.locator('[data-scroll-fade="left"]')).toBeVisible();
  await expect(shortcuts.locator('[data-scroll-fade="right"]')).toHaveCount(0);

  await shortcuts.getByRole('button', { name: '1-day streak' }).focus();
  await expect(shortcuts.locator('[data-scroll-fade="left"]')).toHaveCount(0);
  await expect(shortcuts.locator('[data-scroll-fade="right"]')).toBeVisible();
  await coins.focus();
  await expect(shortcuts.locator('[data-scroll-fade="left"]')).toBeVisible();
  await expect(shortcuts.locator('[data-scroll-fade="right"]')).toHaveCount(0);
});

test('calendar choices fit a phone and download a complete Apple calendar event', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto(`${origin}/e2e/mobile-ui-fixture.html?token=synthetic-do-not-export#private-fragment`);
  const trigger = page.getByRole('button', { name: /add .*science assignment.*to calendar/i });
  await trigger.click();
  const dialog = page.getByRole('dialog');
  const google = dialog.getByRole('link', { name: /Google Calendar/i });
  const apple = dialog.getByRole('button', { name: /Apple Calendar/i });
  await expect(google).toBeInViewport();
  await expect(apple).toBeInViewport();
  for (const choice of [google, apple]) {
    const bounds = await choice.boundingBox();
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(320);
  }
  const href = new URL(await google.getAttribute('href'));
  expect(href.searchParams.get('dates')).toBe('20261231/20270101');
  expect(href.searchParams.get('details')).toContain(`${origin}/quests?tab=study`);
  const pendingDownload = page.waitForEvent('download');
  await apple.click();
  const download = await pendingDownload;
  expect(download.suggestedFilename()).toMatch(/\.ics$/);
  const content = await readFile(await download.path(), 'utf8');
  expect(content).toContain('DTSTART;VALUE=DATE:20261231\r\n');
  expect(content).toContain('DTEND;VALUE=DATE:20270101\r\n');
  expect(content).toContain('END:VCALENDAR\r\n');
  expect(content).not.toContain('synthetic-do-not-export');
  expect(content).not.toContain('private-fragment');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(trigger).toBeFocused();
});
