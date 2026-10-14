import { test, expect } from '@playwright/test';
import { assertPwaDraftProtection, installWaitingWorkerProbe } from './live-smoke/pwa-ux.js';
import { startLivePwaUxFixture } from './live-pwa-ux-fixture.js';

test.use({ serviceWorkers: 'block', trace: 'off', screenshot: 'off', video: 'off', reducedMotion: 'reduce' });
let fixture;
test.beforeAll(async () => { fixture = await startLivePwaUxFixture(); });
test.afterAll(async () => { await fixture?.stop(); });

async function prepare(context, { damageGuards = false } = {}) {
  const external = [];
  await context.route('**/*', route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== fixture.origin || !['GET', 'HEAD'].includes(request.method())) {
      external.push({ method: request.method(), path: url.pathname });
      return route.abort();
    }
    return route.continue();
  });
  await context.addInitScript(({ damageGuards }) => {
    window.__abbyOfflinePwaFault = damageGuards === 'modal' ? 'missing-modal-guard' : damageGuards ? 'missing-guards' : '';
    const countKey = 'offline-live-pwa-native-calls';
    window.__abbyOfflineNativeWorkerCalls = JSON.parse(localStorage.getItem(countKey) || 'null') || { register: 0, update: 0, postMessage: 0 };
    for (const [type, name] of [[window.ServiceWorkerContainer, 'register'], [window.ServiceWorkerRegistration, 'update'], [window.ServiceWorker, 'postMessage']]) {
      if (!type?.prototype) continue;
      Object.defineProperty(type.prototype, name, { configurable: true, value: () => {
        window.__abbyOfflineNativeWorkerCalls[name] += 1;
        localStorage.setItem(countKey, JSON.stringify(window.__abbyOfflineNativeWorkerCalls));
        throw new Error('Native worker API must remain unused in the observer facade');
      } });
    }
  }, { damageGuards });
  await context.addInitScript(installWaitingWorkerProbe);
  return external;
}

async function project(page) {
  await page.goto(`${fixture.origin}/projects/new`);
  await expect(page.getByTestId('fixture-mode')).toHaveText('production');
  await expect(page.getByRole('button', { name: 'Reload', exact: true })).toBeEnabled();
  return page.getByRole('textbox', { name: 'Title', exact: true });
}

async function noNativeWork(page, context, external) {
  expect(await page.evaluate(() => window.__abbyOfflineNativeWorkerCalls)).toEqual({ register: 0, update: 0, postMessage: 0 });
  expect(context.serviceWorkers()).toEqual([]);
  expect(external).toEqual([]);
  expect(fixture.mutations).toEqual([]);
  expect(fixture.requests.some(request => request.path === '/sw.js')).toBe(false);
}

test('trusted PWA helper checks actual production React forms without native workers or product writes', async ({ page, context }) => {
  const external = await prepare(context);
  const result = await assertPwaDraftProtection(page, fixture.origin);
  expect(result).toEqual({ pwaDraftProtection: true, pwaActivationRace: true, pwaActivationFailure: true, pwaFallbackRetry: true });
  await noNativeWork(page, context, external);
});

test('trusted PWA helper rejects missing modal guards after the project guard succeeds', async ({ page, context }) => {
  const external = await prepare(context, { damageGuards: 'modal' });
  await expect(assertPwaDraftProtection(page, fixture.origin)).rejects.toThrow(/toBeDisabled/);
  await expect(page.getByRole('dialog', { name: 'New child', exact: true }).getByRole('textbox', { name: 'Display name', exact: true })).toHaveValue('Local observer draft');
  await noNativeWork(page, context, external);
});

test('trusted PWA helper rejects a real project form whose guard registration is missing', async ({ page, context }) => {
  const external = await prepare(context, { damageGuards: true });
  await expect(assertPwaDraftProtection(page, fixture.origin)).rejects.toThrow(/toBeDisabled/);
  await expect(page.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue('Observer draft kept only in this browser');
  await noNativeWork(page, context, external);
});

test('actual CreateChild modal registers and releases its guard without a save request', async ({ page, context }) => {
  const external = await prepare(context);
  await page.goto(`${fixture.origin}/manage`);
  await page.getByRole('button', { name: 'New child', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New child', exact: true });
  const name = dialog.getByRole('textbox', { name: 'Display name', exact: true });
  await name.fill('Local synthetic child draft');
  const reload = page.getByRole('button', { name: 'Reload', exact: true });
  await expect(reload).toBeDisabled();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByRole('alertdialog', { name: 'Discard changes?' })).toBeVisible();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(name).toHaveValue('Local synthetic child draft');
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(reload).toBeEnabled();
  await noNativeWork(page, context, external);
});

for (const signal of ['controllerchange', 'fallback']) {
  test(`actual provider preserves a draft opened during ${signal} activation`, async ({ page, context }) => {
    const external = await prepare(context);
    const title = await project(page);
    let navigations = 0;
    page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations += 1; });
    await page.getByRole('button', { name: 'Reload', exact: true }).click();
    await title.fill(`Draft retained through ${signal}`);
    if (signal === 'controllerchange') await page.evaluate(() => window.__abbyLivePwaProbe.controlChanged());
    // Include the real 1500ms fallback window, so a late unsafe reload cannot
    // pass a momentary navigation-counter assertion.
    await page.waitForTimeout(1800);
    await expect(title).toHaveValue(`Draft retained through ${signal}`);
    await expect(page.getByRole('button', { name: 'Reload', exact: true })).toBeDisabled();
    expect(navigations).toBe(0);
    expect(await page.evaluate(() => window.__abbyLivePwaProbe.snapshot().posts)).toBe(1);
    await noNativeWork(page, context, external);
  });
}

test('activation failure cancels fallback and a deliberate retry reloads successfully', async ({ page, context }) => {
  const external = await prepare(context);
  const title = await project(page);
  let navigations = 0;
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations += 1; });
  await page.evaluate(() => window.__abbyLivePwaProbe.failNextMessage());
  await page.getByRole('button', { name: 'Reload', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText(/Could not start the app update\. Try again later\./);
  await page.waitForTimeout(1800);
  expect(navigations).toBe(0);
  expect(await page.evaluate(() => window.__abbyLivePwaProbe.snapshot())).toMatchObject({ failedMessages: 1, posts: 0 });
  const loaded = page.waitForEvent('load');
  await page.getByRole('button', { name: 'Reload', exact: true }).click();
  await loaded;
  await expect(title).toHaveValue('');
  await expect(page.getByRole('button', { name: 'Reload', exact: true })).toHaveCount(0);
  await noNativeWork(page, context, external);
});

test('clean controllerchange reloads once and suppresses the repeated update prompt', async ({ page, context }) => {
  const external = await prepare(context);
  await project(page);
  let navigations = 0;
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations += 1; });
  const loaded = page.waitForEvent('load');
  await page.getByRole('button', { name: 'Reload', exact: true }).click();
  await page.evaluate(() => window.__abbyLivePwaProbe.controlChanged());
  await loaded;
  await expect(page.getByRole('textbox', { name: 'Title', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__abbyLivePwaProbe.snapshot().registered)).toBe(1);
  await page.waitForTimeout(1800);
  expect(navigations).toBe(1);
  await expect(page.getByRole('button', { name: 'Reload', exact: true })).toHaveCount(0);
  // The provider consumes the stamp when suppressing the repeated prompt.
  expect(await page.evaluate(() => localStorage.getItem('pwa:last-reload-attempt'))).toBeNull();
  await noNativeWork(page, context, external);
});

test('worker facade validates its protocol and never falls through to native registration', async ({ page, context }) => {
  const external = await prepare(context);
  await project(page);
  const outcomes = await page.evaluate(async () => {
    const failures = [];
    for (const [path, scope] of [['/wrong-worker.js', '/'], ['/sw.js', '/wrong-scope']]) {
      try { await navigator.serviceWorker.register(path, { scope }); } catch { failures.push('registration-rejected'); }
    }
    const registration = await navigator.serviceWorker.getRegistration();
    for (const message of [{ type: 'unexpected' }, { type: 'SKIP_WAITING', extra: true }]) {
      try { registration.waiting.postMessage(message); } catch { failures.push('message-rejected'); }
    }
    return failures;
  });
  expect(outcomes).toEqual(['registration-rejected', 'registration-rejected', 'message-rejected', 'message-rejected']);
  expect(await page.evaluate(() => window.__abbyLivePwaProbe.snapshot())).toMatchObject({ registered: 1, posts: 0 });
  await noNativeWork(page, context, external);
});
