import { expect, test } from '@playwright/test';
import { buildReleases, startServer } from './pwa-fixture';

let fixtures;
let server;

test.beforeAll(async () => {
  fixtures = await buildReleases({ legacyOAuthReleaseA: true });
});

test.afterEach(async () => {
  await server?.stop();
  server = undefined;
});

test.afterAll(async () => {
  await fixtures?.cleanup();
});

// These values describe a synthetic, unfinished authorization request. No
// credentials, codes, tokens or actual callback URLs are needed by this test.
const authorizePath = `/oauth/authorize/?${new URLSearchParams({
  response_type: 'code',
  client_id: 'synthetic-pwa-browser-client',
  redirect_uri: 'http://127.0.0.1:1455/synthetic-callback',
  scope: 'mcp:catalog',
  resource: 'https://abby.bos.lol/mcp',
  code_challenge: 'synthetic-browser-navigation-challenge-123456789',
  code_challenge_method: 'S256',
  state: 'synthetic-browser-navigation-state',
})}`;

async function installWorker(page, origin, label) {
  await page.goto(origin);
  await expect(page.locator('#release')).toHaveText(`Release ${label}`);
  await expect.poll(() => page.evaluate(async () =>
    (await navigator.serviceWorker.getRegistration('/'))?.active?.state)).toBe('activated');
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)).toBe(`${origin}/sw.js`);
}

async function expectDjangoLogin(page, origin, path, expectedNext) {
  const response = await page.goto(`${origin}${path}`);
  expect(response.status()).toBe(200);
  expect(response.fromServiceWorker()).toBe(false);
  await expect(page.getByRole('heading', { name: 'Sign in to Abby', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Username', exact: true })).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.locator('input[name="next"]')).toHaveValue(expectedNext);
  await expect(page.locator('#release')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toBe('/oauth/login/');
}

async function expectAppNavigation(page, context, origin, label) {
  // A similar app route is deliberately not part of the /oauth namespace.
  const response = await page.goto(`${origin}/oauth-help?source=synthetic`);
  expect(response.fromServiceWorker()).toBe(true);
  await expect(page.locator('#release')).toHaveText(`Release ${label}`);
  await context.setOffline(true);
  try {
    const offlineResponse = await page.goto(`${origin}/synthetic/deep-route?tab=offline`);
    expect(offlineResponse.fromServiceWorker()).toBe(true);
    await expect(page.locator('#release')).toHaveText(`Release ${label}`);
  } finally {
    await context.setOffline(false);
  }
}

test('installed worker sends OAuth login and authorization query strings to Django while keeping app navigation', async ({ page, context }) => {
  server = await startServer(fixtures.releases.B);
  const origin = server.origin;
  await installWorker(page, origin, 'B');

  await expectDjangoLogin(page, origin, '/oauth/login/', '/manage');
  await expectDjangoLogin(page, origin,
    `/oauth/login/?${new URLSearchParams({ next: authorizePath })}`, authorizePath);
  await expectDjangoLogin(page, origin, authorizePath, authorizePath);
  expect(new URL(page.url()).searchParams.get('next')).toBe(authorizePath);
  await expectAppNavigation(page, context, origin, 'B');
});

test('existing pre-fix worker gains OAuth routing through the normal update prompt in the same browser profile', async ({ page, context }) => {
  server = await startServer(fixtures.releases.A);
  const origin = server.origin;
  await installWorker(page, origin, 'A');
  // Record the old behavior in the same browser that receives the upgrade.
  const intercepted = await page.goto(`${origin}${authorizePath}`);
  expect(intercepted.fromServiceWorker()).toBe(true);
  await expect(page.locator('#release')).toHaveText('Release A');

  const port = server.port;
  await server.stop();
  server = await startServer(fixtures.releases.B, port);
  // Normal navigation revalidates /sw.js. Do not unregister a worker, clear
  // storage, install one manually or call registration.update() for recovery.
  await page.goto(`${origin}/synthetic/update-route`);
  await expect(page.locator('#release')).toHaveText('Release A');
  await expect(page.getByText('New version available.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reload', exact: true }).click();
  await expect(page.locator('#release')).toHaveText('Release B');
  await expect(page.getByText('New version available.', { exact: true })).toHaveCount(0);

  await expectDjangoLogin(page, origin, authorizePath, authorizePath);
  await expectDjangoLogin(page, origin,
    `/oauth/login/?${new URLSearchParams({ next: authorizePath })}`, authorizePath);
  await expectAppNavigation(page, context, origin, 'B');
});
