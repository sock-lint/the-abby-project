import { expect } from '@playwright/test';

// The observer keeps native service workers blocked so they cannot bypass its
// request fence. Only their browser-side registration/event boundary is fault
// injected: the real deployed React provider and actual forms remain in use.
// This facade never registers, installs or activates a production worker.
export function installWaitingWorkerProbe() {
  const container = new EventTarget();
  const registration = new EventTarget();
  let registered = 0;
  let posts = 0;
  let failedMessages = 0;
  let failNext = false;
  let scriptPath = '';
  let scope = '';
  const active = Object.freeze({ state: 'activated', scriptURL: `${location.origin}/sw.js` });
  const waiting = Object.freeze({
    state: 'installed',
    postMessage(message) {
      if (message?.type !== 'SKIP_WAITING' || Object.keys(message).length !== 1) {
        throw new Error('Unexpected observer worker message');
      }
      if (failNext) {
        failNext = false;
        failedMessages += 1;
        throw new Error('Controlled observer activation failure');
      }
      posts += 1;
    },
  });
  Object.assign(registration, {
    active, waiting, installing: null,
    pushManager: { getSubscription: async () => null },
  });
  Object.assign(container, {
    controller: active,
    ready: Promise.resolve(registration),
    register: async (path, options) => {
      if (path !== '/sw.js' || options?.scope !== '/') throw new Error('Unexpected observer worker registration');
      registered += 1;
      scriptPath = path;
      scope = options.scope;
      return registration;
    },
    getRegistration: async () => registration,
    getRegistrations: async () => [registration],
  });
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: container });
  Object.defineProperty(window, '__abbyLivePwaProbe', {
    value: Object.freeze({
      snapshot: () => ({ registered, posts, failedMessages, scriptPath, scope }),
      controlChanged: () => container.dispatchEvent(new Event('controllerchange')),
      failNextMessage: () => { failNext = true; },
    }),
  });
}

export async function assertPwaDraftProtection(page, baseUrl) {
  // Only the verified parent journey calls this helper. No submit button is
  // clicked; drafts stay in the isolated browser and disappear on context close.
  await page.goto(`${baseUrl}/projects/new`, { waitUntil: 'domcontentloaded' });
  const title = page.getByRole('textbox', { name: 'Title', exact: true });
  const reload = page.getByRole('button', { name: 'Reload', exact: true });
  await expect(title).toBeVisible();
  await expect(reload).toBeEnabled();
  const snapshot = () => page.evaluate(() => window.__abbyLivePwaProbe.snapshot());
  expect(await snapshot()).toMatchObject({ scriptPath: '/sw.js', scope: '/', posts: 0 });

  let navigations = 0;
  const navigation = (frame) => { if (frame === page.mainFrame()) navigations += 1; };
  page.on('framenavigated', navigation);
  try {
    await title.fill('Observer draft kept only in this browser');
    await expect(reload).toBeDisabled();
    await expect(page.getByRole('status').filter({ hasText: 'Finish or close your open work before updating.' })).toBeVisible();
    expect((await snapshot()).posts).toBe(0);
    await expect(title).toHaveValue('Observer draft kept only in this browser');

    // Exercise a real modal consumer as well as the manually owned page form.
    await title.clear();
    await page.goto(`${baseUrl}/manage`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'New child', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'New child', exact: true });
    await dialog.getByRole('textbox', { name: 'Display name', exact: true }).fill('Local observer draft');
    await expect(reload).toBeDisabled();
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(reload).toBeEnabled();

    await page.goto(`${baseUrl}/projects/new`, { waitUntil: 'domcontentloaded' });
    await expect(title).toBeVisible();
    await expect(reload).toBeEnabled();
    const beforeActivation = navigations;
    await reload.click();
    await title.fill('New work opened after update activation');
    await page.evaluate(() => window.__abbyLivePwaProbe.controlChanged());
    await expect(reload).toBeDisabled();
    // Keep the newly opened work guarded beyond the provider's real fallback
    // delay, so an immediate assertion cannot miss a deferred reload.
    await page.waitForTimeout(1_650);
    await expect(title).toHaveValue('New work opened after update activation');
    expect(navigations).toBe(beforeActivation);

    await title.clear();
    await expect(reload).toBeEnabled();
    const refreshed = page.waitForEvent('load');
    await reload.click();
    await refreshed;
    await expect(title).toHaveValue('');
    await expect(reload).toHaveCount(0);

    // A second clean boot removes only the observer's local suppression marker.
    // It does not alter account state or contact an update/activation endpoint.
    await page.evaluate(() => localStorage.removeItem('pwa:last-reload-attempt'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(reload).toBeEnabled();
    await page.evaluate(() => window.__abbyLivePwaProbe.failNextMessage());
    const beforeFailure = navigations;
    await reload.click();
    await expect(page.getByRole('status').filter({ hasText: 'Could not start the app update. Try again later.' })).toBeVisible();
    expect((await snapshot()).failedMessages).toBe(1);
    expect(navigations).toBe(beforeFailure);
    await expect(title).toHaveValue('');
    // Retry is an explicit second choice. No controller event is emitted;
    // this proves the deployed provider's real 1500ms fallback reload path.
    const fallbackReload = page.waitForEvent('load');
    await reload.click();
    await fallbackReload;
    await expect(title).toHaveValue('');
    await expect(reload).toHaveCount(0);
  } finally {
    page.off('framenavigated', navigation);
  }
  return { pwaDraftProtection: true, pwaActivationRace: true, pwaActivationFailure: true, pwaFallbackRetry: true };
}
