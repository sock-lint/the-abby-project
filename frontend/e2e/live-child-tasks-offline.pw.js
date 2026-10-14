import { pathToFileURL } from 'node:url';
import { test, expect } from '@playwright/test';
import { startLiveChildTasksFixture } from './live-child-tasks-fixture.js';

// The optional private baseline module isolates the original child Tasks
// sequence for failure-before evidence. Regular CI uses the current helper.
const helperUrl = process.env.ABBY_CHILD_TASKS_BASE_HELPER
  ? pathToFileURL(process.env.ABBY_CHILD_TASKS_BASE_HELPER).href
  : new URL('./live-smoke/family-task-ux.js', import.meta.url).href;
const { checkChildTasks } = await import(helperUrl);

test.use({ serviceWorkers: 'block', trace: 'off', screenshot: 'off', video: 'off', reducedMotion: 'reduce' });
let fixture;
test.beforeAll(async () => { fixture = await startLiveChildTasksFixture(); });
test.afterAll(async () => { await fixture?.stop(); });

async function prepare(page, context, populated) {
  fixture.setPopulated(populated);
  const denied = [];
  const failed = [];
  await context.route('**/*', (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== fixture.origin || !['GET', 'HEAD'].includes(request.method())) {
      denied.push({ method: request.method(), path: url.pathname });
      return route.abort();
    }
    return route.continue();
  });
  page.on('requestfailed', request => failed.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText }));
  await page.goto(`${fixture.origin}/quests?tab=duties`);
  await expect(page.getByRole('heading', { name: 'Chores', exact: true })).toBeVisible();
  await page.waitForLoadState('networkidle');
  const credentials = { baseUrl: fixture.origin, child: { id: 7 }, parent: { id: 8 } };
  const gate = {
    credentials, role: 'child', verified: true,
    assertSafe() { expect(denied).toEqual([]); expect(fixture.mutations).toEqual([]); },
  };
  return { denied, failed, credentials, gate };
}

function habitReads() {
  return fixture.requests.filter(request => request.path === '/api/habits/' && request.pending !== 'true');
}

for (const populated of [false, true]) {
  test(`actual ${populated ? 'populated' : 'empty'} Tasks run first Habits mount offline and recover using Try again`, async ({ page, context }) => {
    const { failed, credentials, gate } = await prepare(page, context, populated);
    expect(habitReads()).toHaveLength(0);
    const result = await checkChildTasks(page, credentials, gate);
    expect(result).toEqual({
      choresSearch: populated ? 'filtered_and_cleared' : 'verified_true_empty',
      habitsSearch: populated ? 'filtered_and_cleared' : 'verified_true_empty',
      readRecovery: 'offline_retry',
    });
    expect(failed.some(request => request.path === '/api/habits/' && /INTERNET_DISCONNECTED/.test(request.error))).toBe(true);
    expect(habitReads()).toHaveLength(1);
    await expect(page.locator('main').getByRole('alert')).toHaveCount(0);
    expect(context.serviceWorkers()).toEqual([]);
    gate.assertSafe();
  });
}

test('visited actual Habits retain their DOM and data instead of fetching again offline', async ({ page, context }) => {
  const { gate } = await prepare(page, context, true);
  const tabs = page.getByRole('tablist', { name: 'Tasks sections', exact: true });
  await tabs.getByRole('tab', { name: 'Habits', exact: true }).click();
  const search = page.getByRole('searchbox', { name: 'Filter habits', exact: true });
  await expect(search).toBeVisible();
  await search.fill('reading');
  const before = await search.elementHandle();
  await tabs.getByRole('tab', { name: 'Chores', exact: true }).click();
  expect(await before.evaluate(input => input.isConnected)).toBe(true);
  expect(await before.evaluate(input => input.closest('[hidden]') !== null)).toBe(true);
  const reads = habitReads().length;
  try {
    await context.setOffline(true);
    await tabs.getByRole('tab', { name: 'Habits', exact: true }).click();
    await expect(search).toHaveValue('reading');
    expect(await search.evaluate((input, previous) => input === previous, before)).toBe(true);
    await expect(page.locator('main').getByRole('alert')).toHaveCount(0);
    expect(habitReads()).toHaveLength(reads);
  } finally {
    await context.setOffline(false);
    await before.dispose();
  }
  gate.assertSafe();
});

test('actual first-mount Habits failure exposes Try again and recovers without mutation', async ({ page, context }) => {
  const { gate } = await prepare(page, context, false);
  const tabs = page.getByRole('tablist', { name: 'Tasks sections', exact: true });
  try {
    await context.setOffline(true);
    await tabs.getByRole('tab', { name: 'Habits', exact: true }).click();
    const alert = page.locator('main').getByRole('alert').filter({ hasText: "Couldn't load habits." });
    await expect(alert).toBeVisible();
    await expect(alert.getByRole('button', { name: 'Try again', exact: true })).toBeVisible();
    await expect(alert.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0);
    await expect(page.getByText('No habits yet. Add or propose a habit to get started.', { exact: true })).toHaveCount(0);
  } finally { await context.setOffline(false); }
  const buttons = page.locator('main').getByRole('alert').getByRole('button', { name: 'Try again', exact: true });
  while (await buttons.count()) {
    const count = await buttons.count();
    await buttons.first().click();
    await expect(buttons).toHaveCount(count - 1);
  }
  await expect(page.getByText('No habits yet. Add or propose a habit to get started.', { exact: true })).toBeVisible();
  gate.assertSafe();
});

test('actual Forge uses 3D Printing heading and local model controls with an empty budget', async ({ page, context }) => {
  const { gate } = await prepare(page, context, false);
  await page.getByRole('tablist', { name: 'Tasks sections', exact: true })
    .getByRole('tab', { name: '3D Printing', exact: true }).click();
  await expect(page.getByRole('heading', { name: '3D Printing', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Forge', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Ask for a print', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask for a print', exact: true });
  await dialog.getByRole('button', { name: 'Upload', exact: true }).click();
  await dialog.getByLabel('Model file', { exact: true }).setInputFiles({ name: 'offline-local-model.stl', mimeType: 'application/octet-stream', buffer: Buffer.from('solid local\nendsolid local\n') });
  await expect(dialog.getByText('offline-local-model.stl', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Remove model file', exact: true }).click();
  await expect(dialog.getByText('No file selected', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  gate.assertSafe();
});

test('actual Portfolio replaces and removes local photo previews then cancels without upload', async ({ page, context }) => {
  const { gate } = await prepare(page, context, false);
  await page.goto(`${fixture.origin}/chronicle?tab=sketchbook`);
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Upload Photo', exact: true });
  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=', 'base64');
  let previousPreview;
  for (const name of ['offline-local-first.png', 'offline-local-replaced.png']) {
    await dialog.getByLabel('Photo', { exact: true }).setInputFiles({ name, mimeType: 'image/png', buffer: pixel });
    await expect(dialog.getByText(name, { exact: true })).toBeVisible();
    const image = dialog.getByRole('img', { name: 'Photo preview', exact: true });
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate(element => element.complete && element.naturalWidth === 1)).toBe(true);
    const preview = await image.getAttribute('src');
    expect(preview).toMatch(/^blob:/);
    if (previousPreview) expect(preview).not.toBe(previousPreview);
    previousPreview = preview;
  }
  await expect(dialog.getByText('offline-local-first.png', { exact: true })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Remove photo', exact: true }).click();
  await expect(dialog.getByText('No file selected', { exact: true })).toBeVisible();
  await expect(dialog.getByRole('img', { name: 'Photo preview', exact: true })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  gate.assertSafe();
});
