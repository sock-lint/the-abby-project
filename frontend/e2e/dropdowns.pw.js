import { test, expect, devices } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown, dropdownListbox } from './dropdown-helpers.js';

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

async function expectPopupFits(page, popup, width, height) {
  await expect(popup).toBeVisible();
  const bounds = await popup.boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

test('gallery dropdown keyboard navigation previews, cancels and commits choices', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  const subject = page.getByRole('combobox', { name: 'Homework subject', exact: true });
  await expect(subject).toHaveJSProperty('tagName', 'BUTTON');
  await subject.focus();
  await page.keyboard.press('Home');
  await expect(subject).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('ArrowDown');
  await expect(dropdownListbox(subject).locator('[data-active="true"]')).toHaveAttribute('data-value', 'reading');
  await expect(subject).toHaveJSProperty('value', 'math');
  await page.keyboard.press('Escape');
  await expect(subject).toHaveAttribute('aria-expanded', 'false');
  await expect(subject).toHaveJSProperty('value', 'math');
  await expect(subject).toBeFocused();
  await page.keyboard.type('Science');
  await page.keyboard.press('Enter');
  await expect(subject).toHaveJSProperty('value', 'science');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Home');
  await page.keyboard.press('Tab');
  await expect(subject).toHaveJSProperty('value', 'science');
  await expect(subject).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('combobox', { name: 'Activity filter', exact: true })).toBeFocused();

  const grouped = page.getByRole('combobox', { name: 'Grouped activities', exact: true });
  await grouped.focus();
  await page.keyboard.press('End');
  const popup = dropdownListbox(grouped);
  await expect(popup.locator('[data-active="true"]')).toHaveAttribute('data-value', 'walking');
  await expect(popup.getByRole('option', { name: /Swimming/ })).toHaveAttribute('aria-disabled', 'true');
  await page.keyboard.press('Enter');
  await expect(grouped).toHaveJSProperty('value', 'walking');
  await grouped.click();
  await page.getByRole('heading', { name: 'Dropdowns', exact: true }).click();
  await expect(grouped).toHaveAttribute('aria-expanded', 'false');
  await expect(grouped).toHaveJSProperty('value', 'walking');
  await expect(page.getByRole('combobox', { name: 'Unavailable dropdown', exact: true })).toBeDisabled();
});

test.describe('touch dropdowns', () => {
  test.use({ hasTouch: true, isMobile: true });
  test('a touch swipe scrolls the long Homework child menu', async ({ page, context }, info) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(`${origin}/e2e/dropdowns-fixture.html?theme=snowquill`);
    await page.getByRole('button', { name: 'New assignment', exact: true }).tap();
    const dialog = page.getByRole('dialog', { name: 'New assignment', exact: true });
    const child = dialog.getByRole('combobox', { name: 'Assign to', exact: true });
    await child.tap();
    const popup = dropdownListbox(child);
    await expectPopupFits(page, popup, 375, 740);
    const bounds = await popup.boundingBox();
    const session = await context.newCDPSession(page);
    const x = bounds.x + bounds.width / 2;
    const start = bounds.y + bounds.height - 24;
    const distance = bounds.height - 48;
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchStart', touchPoints: [{ x, y: start }],
    });
    for (let step = 1; step <= 10; step++) {
      await session.send('Input.dispatchTouchEvent', {
        type: 'touchMove', touchPoints: [{ x, y: start - distance * step / 10 }],
      });
      // Real gestures span frames so Chromium can apply native pan scrolling.
      await new Promise(resolve => setTimeout(resolve, 16));
    }
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await expect.poll(() => popup.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await expect(child).toHaveJSProperty('value', '');
    await expect(dialog).toBeVisible();
    await page.screenshot({ path: info.outputPath('homework-touch-scroll.png') });
    await session.detach();
  });
  for (const theme of ['hyrule', 'vigil', 'sunlit', 'snowquill', 'verdant', 'harvest']) {
    for (const width of [320, 375]) {
      test(`themed popup wraps long grouped choices at ${width}px on ${theme}`, async ({ page }, info) => {
        await page.setViewportSize({ width, height: 740 });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.goto(`${origin}/e2e/design-gallery-fixture.html?theme=${theme}`);
        await page.evaluate(() => document.fonts.ready);
        const grouped = page.getByRole('combobox', { name: 'Grouped activities', exact: true });
        await grouped.tap();
        const popup = dropdownListbox(grouped);
        await expectPopupFits(page, popup, width, 740);
        const long = popup.locator('[data-value="long"]');
        await expect(long).toContainText('A very long activity name');
        expect((await long.boundingBox()).height).toBeGreaterThan(44);
        expect(await long.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
        for (const option of await popup.getByRole('option').all()) {
          expect((await option.boundingBox()).height).toBeGreaterThanOrEqual(44);
        }
        await expect(popup.getByRole('group', { name: 'Creative', exact: true }).getByRole('option', { name: 'Drawing', exact: true })).toBeVisible();
        const disabled = popup.getByRole('option', { name: /Swimming/ });
        await expect(disabled).toHaveAttribute('aria-disabled', 'true');
        // Reveal the entire row before sending a real touch. A forced locator
        // tap skips stable-layout and hit-target checks while scrolling this
        // clipped row; aria-disabled also makes a normal locator tap wait.
        await disabled.scrollIntoViewIfNeeded();
        await expect(disabled).toBeInViewport({ ratio: 1 });
        const touch = await disabled.evaluate(element => {
          const bounds = element.getBoundingClientRect();
          const x = bounds.x + bounds.width / 2;
          const y = bounds.y + bounds.height / 2;
          return { x, y, hitsOption: element.contains(document.elementFromPoint(x, y)) };
        });
        expect(touch.hitsOption).toBe(true);
        await page.touchscreen.tap(touch.x, touch.y);
        await expect(grouped).toHaveJSProperty('value', 'drawing');
        await expect(popup).toBeVisible();
        await page.screenshot({ path: info.outputPath(`dropdown-${theme}-${width}.png`) });
        await long.tap();
        await expect(grouped).toHaveJSProperty('value', 'long');
        await expect(grouped).toContainText('A very long activity name');
        await expect(grouped).toBeFocused();
        await expect(popup).toHaveCount(0);
      });
    }
  }
});

for (const browserName of ['chromium', 'webkit']) {
  test(`${browserName}: compact menus sit next to the field above and below`, async ({ playwright }, info) => {
    const browser = await playwright[browserName].launch();
    const page = await browser.newPage({ viewport: { width: 513, height: 740 } });
    try {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`${origin}/e2e/dropdowns-fixture.html?compact=1`);
      await page.evaluate(() => document.fonts.ready);
      await page.getByRole('button', { name: 'New assignment', exact: true }).click();
      const child = page.getByRole('combobox', { name: 'Assign to', exact: true });
      await child.click();
      const above = dropdownListbox(child);
      await expect(above.getByRole('option')).toHaveCount(3);
      await expectPopupFits(page, above, 513, 740);
      const triggerBounds = await child.boundingBox();
      const aboveBounds = await above.boundingBox();
      expect(triggerBounds.y - aboveBounds.y - aboveBounds.height).toBeCloseTo(6, 0);
      await page.screenshot({ path: info.outputPath(`homework-compact-${browserName}.png`) });

      await page.goto(`${origin}/e2e/dropdowns-fixture.html?mode=single`);
      const single = page.getByRole('combobox', { name: 'Single choice', exact: true });
      await single.click();
      const below = dropdownListbox(single);
      await expect(below.getByRole('option')).toHaveCount(1);
      const singleBounds = await single.boundingBox();
      const belowBounds = await below.boundingBox();
      expect(belowBounds.y - singleBounds.y - singleBounds.height).toBeCloseTo(6, 0);
      await expectPopupFits(page, below, 513, 740);
    } finally {
      await browser.close();
    }
  });

  test(`${browserName}: listbox escapes sheet clipping and Escape preserves the assignment form`, async ({ playwright }, info) => {
    const browser = await playwright[browserName].launch();
    const page = await browser.newPage();
    try {
      await page.setViewportSize({ width: 320, height: 320 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`${origin}/e2e/dropdowns-fixture.html`);
      const opener = page.getByRole('button', { name: 'New assignment', exact: true });
      await opener.click();
      const dialog = page.getByRole('dialog', { name: 'New assignment', exact: true });
      const child = dialog.getByRole('combobox', { name: 'Assign to', exact: true });
      // Model platforms that do not focus a button when it is clicked. The
      // combobox must own focus before arrow keys or Escape are pressed.
      await child.evaluate(element => element.addEventListener('mousedown', event => event.preventDefault(), { once: true }));
      await child.click();
      await expect(child).toBeFocused();
      const popup = dropdownListbox(child);
      await expectPopupFits(page, popup, 320, 320);
      await page.keyboard.press('End');
      const last = popup.getByRole('option').last();
      await expect(last).toBeInViewport({ ratio: 1 });
      const hit = await last.evaluate(element => {
        const bounds = element.getBoundingClientRect();
        return document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2)?.closest('[role="option"]') === element;
      });
      expect(hit, 'The option must receive pointer hits above the clipped sheet body').toBe(true);
      await page.screenshot({ path: info.outputPath(`homework-${browserName}-short.png`) });
      await page.keyboard.press('Escape');
      await expect(popup).toHaveCount(0);
      await expect(child).toHaveJSProperty('value', '');
      await expect(dialog).toBeVisible();
      await expect(child).toBeFocused();
      await expect(page.getByRole('alertdialog')).toHaveCount(0);
      await page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
      await expect(opener).toBeFocused();
    } finally {
      await browser.close();
    }
  });
}

test('actual Homework dropdowns send the selected subject and child to the API', async ({ page }, info) => {
  const writes = [];
  await page.route('**/api/**', async route => {
    const request = route.request();
    if (!new URL(request.url()).pathname.startsWith('/api/')) return route.continue();
    if (new URL(request.url()).pathname === '/api/homework/' && request.method() === 'POST') {
      writes.push(request.postDataJSON());
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 1 }) });
    }
    return route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"Unexpected fixture API request"}' });
  });
  await page.setViewportSize({ width: 375, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/dropdowns-fixture.html?theme=snowquill`);
  await page.getByRole('button', { name: 'New assignment', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New assignment', exact: true });
  await dialog.getByPlaceholder('Title', { exact: true }).fill('Synthetic science assignment');
  await dialog.locator('input[type="date"]').fill('2099-12-31');
  await chooseDropdown(dialog.getByRole('combobox', { name: 'Subject', exact: true }), 'science');
  const child = dialog.getByRole('combobox', { name: 'Assign to', exact: true });
  await child.click();
  await expect(dropdownListbox(child)).toBeVisible();
  await page.screenshot({ path: info.outputPath('homework-assignment-after.png') });
  await dropdownListbox(child).getByRole('option', { name: 'Alex', exact: true }).click();
  await dialog.getByRole('button', { name: 'Create assignment', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Assignment saved');
  expect(writes).toEqual([{
    title: 'Synthetic science assignment', description: '', subject: 'science',
    due_date: '2099-12-31', effort_level: 3, assigned_to: 21,
  }]);
});

test('required Homework child selection focuses the themed field before any API write', async ({ page }) => {
  const writes = [];
  await page.route('**/api/**', route => {
    if (!new URL(route.request().url()).pathname.startsWith('/api/')) return route.continue();
    writes.push(route.request().url());
    return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/dropdowns-fixture.html`);
  await page.getByRole('button', { name: 'New assignment', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New assignment', exact: true });
  await dialog.getByPlaceholder('Title', { exact: true }).fill('Required field example');
  await dialog.locator('input[type="date"]').fill('2099-12-31');
  await dialog.getByRole('button', { name: 'Create assignment', exact: true }).click();
  const child = dialog.getByRole('combobox', { name: 'Assign to', exact: true });
  await expect(child).toBeFocused();
  await expect(child).toHaveAttribute('aria-invalid', 'true');
  await expect(dialog.getByRole('alert')).toContainText(/select|choose/i);
  expect(writes).toEqual([]);
});

for (const [browserName, device] of [['chromium', 'Pixel 7'], ['webkit', 'iPhone 14']]) {
  test(`${browserName}: touch selections in a focusable sheet commit once without losing the form`, async ({ playwright }, info) => {
    const browser = await playwright[browserName].launch();
    const page = await browser.newPage({ ...devices[device] });
    page.setDefaultTimeout(15_000);
    const writes = [];
    const unexpected = [];
    try {
      await page.route('**/*', route => {
        if (new URL(route.request().url()).origin !== origin) {
          unexpected.push(route.request().url());
          return route.abort();
        }
        return route.continue();
      });
      await page.route('**/api/**', route => {
        const request = route.request();
        if (!new URL(request.url()).pathname.startsWith('/api/')) return route.continue();
        if (new URL(request.url()).pathname === '/api/homework/' && request.method() === 'POST') {
          writes.push(request.postDataJSON());
          return route.fulfill({ json: { id: 1 } });
        }
        unexpected.push(`${request.method()} ${new URL(request.url()).pathname}`);
        return route.abort();
      });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`${origin}/e2e/dropdowns-fixture.html?compact=1`);
      await page.getByRole('button', { name: 'New assignment', exact: true }).tap();
      const dialog = page.getByRole('dialog', { name: 'New assignment', exact: true });
      // A real BottomSheet can receive focus when a compatibility mousedown
      // bubbles from a touch option. Keep selection attached to the field.
      await expect(dialog).toHaveAttribute('tabindex', '-1');
      await dialog.getByPlaceholder('Title', { exact: true }).fill('Synthetic touch assignment');
      await dialog.locator('input[type="date"]').fill('2099-12-31');
      const form = dialog.locator('form');
      await form.evaluate(element => {
        element.dropdownChanges = [];
        element.addEventListener('change', event => {
          if (event.target.tagName === 'SELECT') element.dropdownChanges.push(event.target.value);
        });
      });
      for (const [name, option, value] of [['Assign to', 'Alex', '21'], ['Subject', 'Science', 'science']]) {
        const control = dialog.getByRole('combobox', { name, exact: true });
        await control.tap();
        await expect(control).toBeFocused();
        const popup = dropdownListbox(control);
        await popup.getByRole('option', { name: option, exact: true }).tap();
        await expect(control).toHaveJSProperty('value', value);
        await expect(control).toBeFocused();
        await expect(popup).toHaveCount(0);
        await expect(dialog).toBeVisible();
        await expect(dialog.getByPlaceholder('Title', { exact: true })).toHaveValue('Synthetic touch assignment');
      }
      expect(await form.evaluate(element => element.dropdownChanges)).toEqual(['21', 'science']);
      expect(writes).toEqual([]);
      await page.screenshot({ path: info.outputPath(`touch-sheet-${browserName}.png`) });
      await dialog.getByRole('button', { name: 'Create assignment', exact: true }).tap();
      await expect(page.getByRole('status')).toHaveText('Assignment saved');
      expect(writes).toEqual([{
        title: 'Synthetic touch assignment', description: '', subject: 'science',
        due_date: '2099-12-31', effort_level: 3, assigned_to: 21,
      }]);
      expect(unexpected).toEqual([]);
    } finally {
      await browser.close();
    }
  });
}
