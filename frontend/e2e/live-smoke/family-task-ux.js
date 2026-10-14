import { expect } from '@playwright/test';
import { requireCheck } from '../../scripts/live-checks-contract.mjs';

const WAIT = 6_000;
const NO_MATCH = 'abby-live-local-no-match-7f628a';

function scope(page, credentials, gate, role) {
  requireCheck(gate.verified && gate.role === role && gate.credentials === credentials, 'ISOLATION');
  requireCheck(new URL(page.url()).origin === credentials.baseUrl, 'ISOLATION');
  return credentials.baseUrl;
}

async function visit(page, base, path) {
  await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main')).toBeVisible({ timeout: WAIT });
}

function memoryRequests(page, childId) {
  let invalid = false;
  const inspect = (request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/chronicle/')) return;
    const selected = url.searchParams.get('user_id');
    if (selected !== null && selected !== String(childId)) invalid = true;
  };
  page.on('request', inspect);
  return {
    check: () => requireCheck(!invalid, 'ISOLATION'),
    close: () => page.off('request', inspect),
  };
}

async function memoryTab(page, name, childId, parent) {
  await page.getByRole('tablist', { name: 'Memories sections', exact: true })
    .getByRole('tab', { name, exact: true }).click();
  if (parent) {
    await expect(page.getByRole('combobox', { name: 'Viewing', exact: true })).toHaveValue(String(childId), { timeout: WAIT });
    await expect(page).toHaveURL((url) => url.searchParams.get('child') === String(childId));
  } else {
    await expect(page.getByRole('combobox', { name: 'Viewing', exact: true })).toHaveCount(0);
  }
  await expect(page.locator('main').getByRole('alert')).toHaveCount(0, { timeout: WAIT });
}

async function taskSearch(page, name, emptyText) {
  const main = page.locator('main');
  const search = main.getByRole('searchbox', { name: `Filter ${name}`, exact: true });
  const empty = main.getByText(emptyText, { exact: true });
  await expect(search.or(empty)).toBeVisible({ timeout: WAIT });
  await expect(main.getByRole('alert')).toHaveCount(0);
  if (await empty.isVisible()) {
    await expect(search).toHaveCount(0);
    return 'verified_true_empty';
  }
  await search.fill(NO_MATCH);
  await expect(main.getByText(`No matches for “${NO_MATCH}”`, { exact: true })).toBeVisible({ timeout: WAIT });
  await main.getByRole('button', { name: 'Clear filter', exact: true }).last().click();
  await expect(search).toHaveValue('');
  await expect(main.getByText(/No matches for/)).toHaveCount(0);
  return 'filtered_and_cleared';
}

async function projectReturn(page, base, gate) {
  // Existing records stay untouched. An empty fixture is an explicit outcome,
  // rather than evidence that detail/back behavior was exercised.
  const response = page.waitForResponse((reply) => {
    const url = new URL(reply.url());
    return url.origin === base && url.pathname === '/api/projects/' && reply.request().method() === 'GET';
  });
  void response.catch(() => {});
  await visit(page, base, '/quests?tab=ventures');
  const loaded = await response;
  requireCheck(loaded.status() === 200, 'BROWSER');
  const body = await loaded.json();
  const rows = Array.isArray(body) ? body : body?.results;
  requireCheck(Array.isArray(rows), 'BROWSER');
  const main = page.locator('main');
  const cards = main.getByRole('button', { name: /^Open / });
  const empty = main.getByText(/^No projects yet\./);
  await expect(cards.first().or(empty)).toBeVisible({ timeout: WAIT });
  await expect(main.getByRole('alert')).toHaveCount(0);
  if (await empty.isVisible()) {
    requireCheck(rows.length === 0 && !body?.next && (body?.count == null || body.count === 0), 'BROWSER');
    await expect(cards).toHaveCount(0);
    gate.assertSafe();
    return 'verified_true_empty';
  }
  requireCheck(rows.length > 0, 'BROWSER');
  const label = await cards.first().getAttribute('aria-label');
  requireCheck(label?.startsWith('Open ') && label.length > 5, 'BROWSER');
  const row = rows.find((item) => item.title === label.slice(5));
  requireCheck(row && ['draft', 'in_progress', 'in_review', 'completed'].includes(row.status)
    && ['required', 'bounty'].includes(row.payment_kind), 'BROWSER');
  await main.getByRole('combobox', { name: 'Filter by status', exact: true }).selectOption(row.status);
  await main.getByRole('combobox', { name: 'Filter by type', exact: true }).selectOption(row.payment_kind);
  if (gate.role === 'parent') {
    requireCheck(row.assigned_to == null || row.assigned_to.id === gate.credentials.child.id, 'ISOLATION');
    await main.getByRole('combobox', { name: 'Filter by child', exact: true })
      .selectOption(row.assigned_to == null ? 'unassigned' : String(row.assigned_to.id));
  }
  const search = main.getByRole('searchbox', { name: 'Filter projects', exact: true });
  await search.fill(label.slice(5, 261));
  await expect(page).toHaveURL((url) => url.searchParams.get('q') === label.slice(5, 261));
  const card = main.getByRole('button', { name: label, exact: true }).first();
  await card.scrollIntoViewIfNeeded();
  const savedSearch = new URL(page.url()).search;
  const savedTop = await page.evaluate(() => window.scrollY);
  const restoredFilters = async () => {
    await expect(main.getByRole('combobox', { name: 'Filter by status', exact: true })).toHaveValue(row.status);
    await expect(main.getByRole('combobox', { name: 'Filter by type', exact: true })).toHaveValue(row.payment_kind);
    if (gate.role === 'parent') await expect(main.getByRole('combobox', { name: 'Filter by child', exact: true }))
      .toHaveValue(row.assigned_to == null ? 'unassigned' : String(row.assigned_to.id));
  };
  await card.click();
  await expect(page).toHaveURL((url) => /^\/quests\/ventures\/\d+$/.test(url.pathname));
  const back = page.getByRole('link', { name: 'Back to Projects', exact: true });
  await expect(back).toHaveAttribute('href', `/quests${savedSearch}`, { timeout: WAIT });
  await back.click();
  await expect(page).toHaveURL((url) => url.pathname === '/quests' && url.search === savedSearch);
  await expect(search).toHaveValue(label.slice(5, 261), { timeout: WAIT });
  await restoredFilters();
  await expect.poll(() => page.evaluate((top) => Math.abs(window.scrollY - top), savedTop), { timeout: WAIT }).toBeLessThanOrEqual(4);
  await expect(main.getByRole('button', { name: label, exact: true }).first()).toBeVisible();
  // Browser Back uses a separate history entry from the explicit return link.
  await main.getByRole('button', { name: label, exact: true }).first().click();
  await expect(page).toHaveURL((url) => /^\/quests\/ventures\/\d+$/.test(url.pathname));
  await page.goBack({ waitUntil: 'domcontentloaded' });
  await expect(page).toHaveURL((url) => url.pathname === '/quests' && url.search === savedSearch);
  await expect(search).toHaveValue(label.slice(5, 261), { timeout: WAIT });
  await restoredFilters();
  await expect.poll(() => page.evaluate((top) => Math.abs(window.scrollY - top), savedTop), { timeout: WAIT }).toBeLessThanOrEqual(4);
  gate.assertSafe();
  return 'detail_and_back';
}

async function offlineHabitRead(page, gate) {
  const tabs = page.getByRole('tablist', { name: 'Tasks sections', exact: true });
  // Preload both route chunks while connected. The offline step only switches
  // the SPA tab; it never performs an offline document navigation or sign-in.
  await tabs.getByRole('tab', { name: 'Chores', exact: true }).click();
  await expect(page.locator('main').getByRole('heading', { name: 'Chores', exact: true })).toBeVisible();
  await expect(page.locator('main').getByRole('searchbox', { name: 'Filter chores', exact: true })
    .or(page.locator('main').getByText('No chores available today.', { exact: true }))).toBeVisible({ timeout: WAIT });
  await expect(page.locator('main').getByText('Loading chore completions…', { exact: true })).toHaveCount(0, { timeout: WAIT });
  await expect(page.locator('main').getByRole('alert')).toHaveCount(0);
  const context = page.context();
  const error = page.locator('main').getByRole('alert').filter({ hasText: "Couldn't load habits." });
  try {
    await context.setOffline(true);
    await tabs.getByRole('tab', { name: 'Habits', exact: true }).click();
    await expect(error).toBeVisible({ timeout: WAIT });
    await expect(error.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
    await expect(page.locator('main').getByText('No habits yet. Add or propose a habit to get started.', { exact: true })).toHaveCount(0);
  } finally {
    await context.setOffline(false);
  }
  // Other parallel read sources can fail in the same offline interval too.
  // Restore them through their actual Retry actions, bounded to this page.
  const retries = page.locator('main').getByRole('alert').getByRole('button', { name: 'Retry', exact: true });
  const count = await retries.count();
  requireCheck(count >= 1 && count <= 5, 'BROWSER');
  const recovered = page.waitForResponse((reply) => {
    const url = new URL(reply.url());
    return url.origin === gate.credentials.baseUrl && url.pathname === '/api/habits/' && reply.request().method() === 'GET';
  });
  void recovered.catch(() => {});
  for (let index = 0; index < count; index += 1) {
    await retries.first().click();
    await expect(retries).toHaveCount(count - index - 1, { timeout: WAIT });
  }
  requireCheck((await recovered).status() === 200, 'BROWSER');
  await expect(page.locator('main').getByRole('alert')).toHaveCount(0, { timeout: WAIT });
  await expect(page.locator('main').getByRole('searchbox', { name: 'Filter habits', exact: true })
    .or(page.locator('main').getByText('No habits yet. Add or propose a habit to get started.', { exact: true }))).toBeVisible({ timeout: WAIT });
  gate.assertSafe();
  return 'offline_retry';
}

async function localAttachments(page, base, gate) {
  await visit(page, base, '/chronicle?tab=sketchbook');
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  const photo = page.getByRole('dialog', { name: 'Upload Photo', exact: true });
  // A synthetic transparent pixel remains a local File/blob. Never submit it.
  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=', 'base64');
  for (const name of ['abby-live-local-first.png', 'abby-live-local-replaced.png']) {
    await photo.getByLabel('Photo', { exact: true }).setInputFiles({ name, mimeType: 'image/png', buffer: pixel });
    await expect(photo.getByText(name, { exact: true })).toBeVisible();
    await expect(photo.getByRole('img', { name: 'Photo preview', exact: true })).toBeVisible();
    await expect.poll(() => photo.getByRole('img', { name: 'Photo preview', exact: true }).evaluate((image) => image.complete && image.naturalWidth > 0), { timeout: WAIT }).toBe(true);
  }
  await expect(photo.getByText('abby-live-local-first.png', { exact: true })).toHaveCount(0);
  await photo.getByRole('button', { name: 'Remove photo', exact: true }).click();
  await expect(photo.getByText('No file selected', { exact: true })).toBeVisible();
  await photo.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(photo).toHaveCount(0);
  await visit(page, base, '/quests?tab=forge');
  await page.getByRole('button', { name: 'Ask for a print', exact: true }).click();
  const model = page.getByRole('dialog', { name: 'Ask for a print', exact: true });
  await model.getByRole('button', { name: 'Upload', exact: true }).click();
  for (const name of ['abby-live-local-first.stl', 'abby-live-local-replaced.stl']) {
    await model.getByLabel('Model file', { exact: true }).setInputFiles({ name, mimeType: 'application/octet-stream', buffer: Buffer.from('solid local\nendsolid local\n') });
    await expect(model.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(model.getByText('abby-live-local-first.stl', { exact: true })).toHaveCount(0);
  await model.getByRole('button', { name: 'Remove model file', exact: true }).click();
  await expect(model.getByText('No file selected', { exact: true })).toBeVisible();
  await model.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(model).toHaveCount(0);
  gate.assertSafe();
  return 'local_only';
}

export async function checkParentUx(page, credentials, gate) {
  const base = scope(page, credentials, gate, 'parent');
  const requests = memoryRequests(page, credentials.child.id);
  try {
    await visit(page, base, '/');
    const timeline = page.locator('main').getByRole('button', { name: /^View .+'s timeline$/ });
    await expect(timeline).toHaveCount(1, { timeout: WAIT });
    await timeline.click();
    await expect(page).toHaveURL((url) => url.pathname === '/chronicle' && url.searchParams.get('child') === String(credentials.child.id));
    const viewing = page.getByRole('combobox', { name: 'Viewing', exact: true });
    await expect(viewing).toHaveValue(String(credentials.child.id));
    await expect(viewing.getByRole('option')).toHaveCount(1);
    for (const name of ['Journal', 'Grades', 'Timeline']) await memoryTab(page, name, credentials.child.id, true);
    await visit(page, base, '/chronicle?tab=journal&child=0');
    await expect(viewing).toHaveValue(String(credentials.child.id));
    await expect(viewing.getByRole('option')).toHaveCount(1);
    requests.check();
    gate.assertSafe();
    return { memoryContext: 'verified_parent', invalidChild: 'verified_roster_recovery', projectReturn: await projectReturn(page, base, gate) };
  } finally { requests.close(); }
}

export async function checkChildUx(page, credentials, gate) {
  const base = scope(page, credentials, gate, 'child');
  const requests = memoryRequests(page, credentials.child.id);
  try {
    await visit(page, base, '/chronicle?tab=journal&child=0');
    await expect(page.getByRole('button', { name: /^(Write|Edit) today’s entry$/ })).toBeVisible({ timeout: WAIT });
    for (const name of ['Grades', 'Timeline', 'Journal']) await memoryTab(page, name, credentials.child.id, false);
    requests.check();
    await visit(page, base, '/quests?tab=duties');
    const choresSearch = await taskSearch(page, 'chores', 'No chores available today.');
    await page.getByRole('tablist', { name: 'Tasks sections', exact: true }).getByRole('tab', { name: 'Habits', exact: true }).click();
    const habitsSearch = await taskSearch(page, 'habits', 'No habits yet. Add or propose a habit to get started.');
    const readRecovery = await offlineHabitRead(page, gate);
    const projects = await projectReturn(page, base, gate);
    await visit(page, base, '/quests?tab=movement');
    await expect(page.locator('main').getByText(/^\d+ sessions? recorded today · \d+ XP earned$/, { exact: true })).toBeVisible({ timeout: WAIT });
    await expect(page.locator('main').getByRole('alert')).toHaveCount(0);
    const attachments = await localAttachments(page, base, gate);
    gate.assertSafe();
    return { memoryContext: 'self_scoped', choresSearch, habitsSearch, readRecovery, projectReturn: projects, movementOutcome: 'recorded_and_xp_summary', attachments };
  } finally { requests.close(); }
}
