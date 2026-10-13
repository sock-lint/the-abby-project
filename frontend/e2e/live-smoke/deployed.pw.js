import { expect, test } from '@playwright/test';
import {
  addFailure, LIVE_BASE_URL, LiveCheckError, newResult, readPrivateJson, requireCheck,
  sanitizedResult, validateCredentials, validateDeploymentProof, validateHealth,
  validateIdentity, writePrivateJson,
} from '../../scripts/live-checks-contract.mjs';
import { installRequestGate, RequestGate } from './request-gate';

function isApiResponse(response, path, method = 'GET') {
  const url = new URL(response.url());
  return url.origin === LIVE_BASE_URL && url.pathname === path && response.request().method() === method;
}

async function successfulBody(response, code) {
  requireCheck(response.status() === 200, code);
  return response.json();
}

async function freshContext(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block', reducedMotion: 'reduce',
    viewport: { width: 1280, height: 800 }, acceptDownloads: false, ignoreHTTPSErrors: false });
  context.setDefaultTimeout(12_000);
  context.setDefaultNavigationTimeout(15_000);
  return context;
}

function exactChildren(body, credentials) {
  const rows = Array.isArray(body) ? body : body?.results;
  requireCheck(Array.isArray(rows) && rows.length === 1 && !body?.next
    && rows[0].id === credentials.child.id && rows[0].username === credentials.child.username
    && rows[0].role === 'child', 'ISOLATION');
}

async function checkHealth(request, expectedCommit) {
  const response = await request.get(`${LIVE_BASE_URL}/health`, {
    maxRedirects: 0, timeout: 10_000, headers: { 'Cache-Control': 'no-cache' },
  });
  const body = await successfulBody(response, 'HEALTH');
  requireCheck(response.headers()['cache-control']?.split(',').map((part) => part.trim()).includes('no-store'), 'HEALTH');
  return validateHealth(body, expectedCommit);
}

async function publicShell(browser, credentials, result) {
  const context = await freshContext(browser);
  const gate = new RequestGate(credentials, 'parent');
  await installRequestGate(context, gate);
  try {
    const page = await context.newPage();
    const loaded = new Set();
    page.on('response', (response) => {
      const url = new URL(response.url());
      if (url.origin === LIVE_BASE_URL && url.pathname.startsWith('/static/assets/')
        && response.status() >= 200 && response.status() < 300) {
        if (url.pathname.endsWith('.js')) loaded.add('js');
        if (url.pathname.endsWith('.css')) loaded.add('css');
      }
    });
    const response = await page.goto(`${LIVE_BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
    requireCheck(response?.status() === 200 && new URL(page.url()).origin === LIVE_BASE_URL, 'PUBLIC_SHELL');
    const etag = response.headers().etag?.replace(/^"|"$/g, '');
    if (/^[a-f0-9]{32}$/i.test(etag || '')) result.spaEtag = etag;
    await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
    await expect.poll(() => loaded.has('js') && loaded.has('css')).toBe(true);
    await page.getByRole('link', { name: 'About The Abby Project', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Keep your memories\.\s*Grow your story\./);
    await page.goto(`${LIVE_BASE_URL}/privacy/`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Privacy policy', exact: true })).toBeVisible();
    gate.assertSafe();
  } finally {
    gate.cancel();
    await context.close();
  }
}

async function signin(context, gate, credentials, role, cleanup) {
  const actor = credentials[role];
  const page = await context.newPage();
  await page.goto(`${LIVE_BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('Username', { exact: true }).fill(actor.username);
  await page.getByLabel('Password', { exact: true }).fill(actor.password);
  const loginResponse = page.waitForResponse((response) => isApiResponse(response, '/api/auth/', 'POST'));
  void loginResponse.catch(() => {});
  const dashboardResponse = page.waitForResponse((response) => isApiResponse(response, '/api/dashboard/'));
  // A rejected login has no dashboard request. Consume that wait's rejection
  // without changing the observable failure or permitting another login.
  void dashboardResponse.catch(() => {});
  try {
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const body = await successfulBody(await loginResponse, 'IDENTITY');
    // Validation must finish before a token is eligible for reads or cleanup.
    // A foreign identity never receives a subsequent logout from this suite.
    cleanup.tokens.push(gate.accept(body));
  } catch (error) {
    cleanup.unverifiedIdentity = gate.loginDispatched;
    gate.cancel();
    throw error;
  }
  const dashboard = await successfulBody(await dashboardResponse, role === 'parent' ? 'PARENT' : 'CHILD');
  requireCheck(dashboard.role === role, 'IDENTITY');
  if (role === 'parent') requireCheck(dashboard.children_count === 1, 'ISOLATION');
  await expect(page.locator('main').getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
  gate.assertSafe();
  const meResponse = page.waitForResponse((response) => isApiResponse(response, '/api/auth/me/'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  validateIdentity(await successfulBody(await meResponse, 'IDENTITY'), credentials, role);
  await expect(page.locator('main').getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
  return page;
}

async function parentFlow(browser, request, credentials, cleanup) {
  const context = await freshContext(browser);
  const gate = new RequestGate(credentials, 'parent');
  await installRequestGate(context, gate);
  try {
    const page = await signin(context, gate, credentials, 'parent', cleanup);
    const childrenResponse = page.waitForResponse((response) => isApiResponse(response, '/api/children/'));
    await page.getByRole('link', { name: 'Manage', exact: true }).click();
    await expect(page.locator('main').getByRole('heading', { name: 'Manage', exact: true })).toBeVisible();
    exactChildren(await successfulBody(await childrenResponse, 'ISOLATION'), credentials);
    await expect(page.getByText(`@${credentials.child.username}`, { exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Admin', exact: true })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Test', exact: true })).toHaveCount(0);
    const staffDenied = await request.get(`${LIVE_BASE_URL}/api/admin/families/`, {
      headers: { Authorization: `Token ${gate.token}` }, maxRedirects: 0, timeout: 10_000,
    });
    requireCheck(staffDenied.status() === 403, 'ISOLATION');
    gate.assertSafe();
  } finally {
    gate.cancel();
    await context.close();
  }
}

async function childFlow(browser, request, credentials, cleanup) {
  const context = await freshContext(browser);
  const gate = new RequestGate(credentials, 'child');
  await installRequestGate(context, gate);
  try {
    const page = await signin(context, gate, credentials, 'child', cleanup);
    await expect(page.getByRole('link', { name: 'Manage', exact: true })).toHaveCount(0);
    await page.getByRole('navigation', { name: 'Main navigation', exact: true })
      .getByRole('link', { name: 'Tasks', exact: true }).click();
    await expect(page).toHaveURL((url) => url.origin === LIVE_BASE_URL && url.pathname === '/quests');
    const tasks = page.getByRole('tablist', { name: 'Tasks sections', exact: true });
    await expect(tasks).toBeVisible();
    const homework = tasks.getByRole('tab', { name: 'Homework', exact: true });
    await expect(homework).toBeVisible();
    await expect(homework).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('main').getByRole('heading', { name: 'Homework', exact: true })).toBeVisible();
    const denied = await request.get(`${LIVE_BASE_URL}/api/children/`, {
      headers: { Authorization: `Token ${gate.token}` }, maxRedirects: 0, timeout: 10_000,
    });
    requireCheck(denied.status() === 403, 'ISOLATION');
    await page.goto(`${LIVE_BASE_URL}/sigil`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('main').getByText('Your profile', { exact: true })).toBeVisible();
    await expect(page.locator('main').getByRole('link', { name: 'Edit account & settings', exact: true })).toBeVisible();
    gate.assertSafe();
  } finally {
    gate.cancel();
    await context.close();
  }
}

async function revokeTokens(request, tokens) {
  let clean = true;
  for (const token of tokens) {
    try {
      const logout = await request.post(`${LIVE_BASE_URL}/api/auth/`, {
        headers: { Authorization: `Token ${token}` }, data: { action: 'logout' },
        maxRedirects: 0, timeout: 5_000,
      });
      requireCheck(logout.status() === 200 && (await logout.json()).ok === true, 'CLEANUP');
      const revoked = await request.get(`${LIVE_BASE_URL}/api/auth/me/`, {
        headers: { Authorization: `Token ${token}` }, maxRedirects: 0, timeout: 5_000,
      });
      requireCheck(revoked.status() === 401, 'CLEANUP');
    } catch { clean = false; }
  }
  return clean;
}

test('deployed app serves the expected release and dedicated family workflows', async ({ browser, request }) => {
  const expectedCommit = process.env.ABBY_LIVE_EXPECTED_COMMIT;
  const credentials = validateCredentials(await readPrivateJson(process.env.ABBY_LIVE_CREDENTIALS_FILE));
  const proof = validateDeploymentProof(await readPrivateJson(process.env.ABBY_LIVE_DEPLOYMENT_PROOF_FILE), expectedCommit);
  const result = newResult({ expectedCommit, sourceCommit: process.env.ABBY_LIVE_SOURCE_COMMIT, proof, credentials });
  const cleanup = { tokens: [], unverifiedIdentity: false };
  let stage = 'DEPLOYMENT_PROOF';
  try {
    result.checks.deployment = true;
    stage = 'HEALTH';
    result.servedCommit = await checkHealth(request, expectedCommit);
    stage = 'PUBLIC_SHELL';
    await publicShell(browser, credentials, result);
    result.checks.publicShell = true;
    stage = 'PARENT';
    await parentFlow(browser, request, credentials, cleanup);
    result.checks.parent = true;
    stage = 'CHILD';
    await childFlow(browser, request, credentials, cleanup);
    result.checks.child = true;
    result.checks.isolation = true;
    stage = 'HEALTH';
    result.servedCommit = await checkHealth(request, expectedCommit);
    validateDeploymentProof(proof, expectedCommit);
    result.checks.health = true;
  } catch (error) {
    addFailure(result, error instanceof LiveCheckError ? error.code : stage);
  } finally {
    const revoked = await revokeTokens(request, cleanup.tokens);
    result.checks.cleanup = revoked && !cleanup.unverifiedIdentity;
    if (!result.checks.cleanup) addFailure(result, 'CLEANUP');
    result.checkedAt = new Date().toISOString();
    result.expiresAt = new Date(Math.min(Date.parse(proof.expiresAt), Date.parse(result.checkedAt) + 5 * 60_000)).toISOString();
    try { validateDeploymentProof(proof, expectedCommit); }
    catch { addFailure(result, 'DEPLOYMENT_PROOF'); }
    await writePrivateJson(process.env.ABBY_LIVE_RESULT_FILE, sanitizedResult(result));
  }
  requireCheck(sanitizedResult(result).status === 'passed', 'RUNNER');
});
