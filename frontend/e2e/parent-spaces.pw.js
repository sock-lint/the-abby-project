import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

let server;
let origin;
let fixtures;
const PERSONAL_NAV = ['Today', 'Tasks', 'Pets', 'Rewards', 'Progress', 'Memories'];
const FAMILY_NAV = ['Today', 'Tasks', 'Children', 'Rewards'];

test.beforeAll(async () => {
  const names = ['parent-personal-dashboard', 'parent-family-overview', 'family-child-overview',
    'auth-me-ordinary-parent', 'auth-me-child', 'dashboard-earned-identity', 'parent-personal-project-rate-default'];
  fixtures = Object.fromEntries(await Promise.all(names.map(async (name) => [name,
    JSON.parse(await readFile(new URL(`../../contracts/api/fixtures/${name}.json`, import.meta.url), 'utf8')),
  ])));
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)),
    '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Vite startup timed out: ${output}`)), 30_000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const url = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (url) { clearTimeout(timer); resolve(url[0]); }
    });
    server.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const stopped = once(server, 'exit');
    server.kill();
    await stopped;
  }
});

async function mockApp(page, { child = false, notifications = [] } = {}) {
  const reads = [];
  const writes = [];
  const errors = [];
  const unexpected = [];
  const identity = fixtures[child ? 'auth-me-child' : 'auth-me-ordinary-parent'];
  const personal = fixtures['parent-personal-dashboard'];
  const ownProject = { ...fixtures['parent-personal-project-rate-default'], assigned_to: identity, created_by: identity };
  const ownChore = { id: 711, title: 'My personal chore', assigned_to: identity.id, is_active: true,
    is_available: true, recurrence: 'daily', reward_amount: '0.00', coin_reward: 5, skill_tags: [],
    today_status: null, is_done: false };
  let createdHabit = null;
  const ownHabit = { id: 901, user: identity.id, name: 'Read after breakfast', icon: '', habit_type: 'positive',
    max_taps_per_day: 1, strength: 0, taps_today: 0, xp_reward: 5, skill_tags: [], is_active: true, pending_parent_review: false };
  page.on('pageerror', (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-parent-space-browser-session'));
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      unexpected.push({ url: route.request().url(), method: route.request().method() });
      return route.abort();
    }
    return route.continue();
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/')) return route.fallback();
    const record = { path: url.pathname, query: Object.fromEntries(url.searchParams),
      space: request.headers()['x-abby-space'], authorization: request.headers().authorization };
    if (request.method() === 'POST' && url.pathname === '/api/usage/visit/') return route.fulfill({ status: 204 });
    if (request.method() === 'POST' && url.pathname === '/api/habits/') {
      const body = request.postDataJSON();
      writes.push({ ...record, body });
      createdHabit = { ...ownHabit, ...body, id: 902 };
      return route.fulfill({ status: 201, json: createdHabit });
    }
    if (request.method() !== 'GET') {
      unexpected.push({ path: url.pathname, method: request.method() });
      return route.abort();
    }
    reads.push(record);
    if (url.pathname === '/api/dashboard/') return route.fulfill({ json: child ? fixtures['dashboard-earned-identity']
      : record.space === 'personal' ? personal : fixtures['parent-family-overview'] });
    if (url.pathname === '/api/habits/') return route.fulfill({
      json: url.searchParams.has('pending') ? [] : [ownHabit, ...(createdHabit ? [createdHabit] : [])],
    });
    if (url.pathname === '/api/chores/') return route.fulfill({
      json: url.searchParams.has('pending') ? [] : [ownChore],
    });
    const payloads = {
      '/api/auth/me/': identity,
      '/api/children/': [{ id: 7, username: 'synthetic-abby', display_name: 'Abby', role: 'child', is_active: true },
        { id: 8, username: 'synthetic-ben', display_name: 'Ben', role: 'child', is_active: true }],
      '/api/children/7/overview/': fixtures['family-child-overview'],
      '/api/pulse/': { unread_count: 0, notifications, recent_drops: [], challenge_receipts: [],
        companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [],
        header: { active_timer: null, coin_balance: 35, streak_days: 0, identity: personal.rpg.identity } },
      '/api/sprites/catalog/': { sprites: {}, etag: 'synthetic-empty' },
      '/api/push/config/': { enabled: false },
      '/api/dev/ping/': { enabled: false },
      '/api/coins/': { balance: 35, recent: [] },
      '/api/balance/': { balance: 0, breakdown: {}, recent_transactions: [] },
      '/api/clock/': null,
      '/api/homework/dashboard/': { pending_submissions: [], assignments: [], children: [] },
      '/api/habits/history/': {},
      '/api/pets/stable/': { pets: [], mounts: [], expeditions: [] },
      '/api/challenges/': { results: [], pin: null, daily_bonus: null, locked_catalog: [], recent_receipts: [] },
      '/api/achievements/summary/': { total_xp: 0, skills_count: 0, badges_count: 0 },
      '/api/projects/917/': ownProject,
    };
    return route.fulfill({ json: payloads[url.pathname] ?? [] });
  });
  return { reads, writes, errors, unexpected };
}

function visibleNav(page, width) {
  return width >= 1024 ? page.locator('aside nav[aria-label="Main navigation"]')
    : page.locator('[data-journal-bottom-nav="true"]');
}
async function assertNavigation(page, width, names) {
  const nav = visibleNav(page, width);
  await expect(nav).toBeVisible();
  await expect(nav.getByRole('link')).toHaveCount(names.length);
  for (const name of names) await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
}
async function assertFits(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

for (const width of [320, 390, 1280]) {
  test(`parent switches between Family and own full experience at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const { reads, writes, errors, unexpected } = await mockApp(page);
    await page.goto(`${origin}/`);
    const family = page.locator('button[aria-pressed]').filter({ hasText: /^Family/ });
    const personal = page.getByRole('button', { name: 'My space', exact: true });
    await expect(family).toHaveAttribute('aria-pressed', 'true');
    await assertNavigation(page, width, FAMILY_NAV);
    await expect(page.getByRole('heading', { name: 'Family overview' })).toBeVisible();
    const switcher = page.getByRole('group', { name: 'Choose your space' });
    await expect(switcher.getByRole('button')).toHaveCount(2);
    const track = switcher.locator('[data-space-track]');
    await expect(track).toHaveCount(1);
    const switcherBox = await switcher.boundingBox();
    const trackBox = await track.boundingBox();
    const rowBox = await switcher.locator('..').boundingBox();
    if (width < 1024) {
      expect(trackBox.width).toBe(208);
      expect(trackBox.height).toBe(32);
      expect(switcherBox.height).toBe(44);
      expect(rowBox.height).toBe(48);
    } else {
      expect(trackBox.width).toBe(448);
      expect(trackBox.height).toBe(52);
      expect(rowBox.height).toBe(64);
    }
    const gutter = width < 1024 ? 2 : 4;
    const trackRadius = await track.evaluate(element => parseFloat(getComputedStyle(element).borderTopLeftRadius));
    const effectiveTrackRadius = Math.min(trackRadius, trackBox.height / 2, trackBox.width / 2);
    for (const button of await switcher.getByRole('button').all()) {
      const box = await button.boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.x).toBeGreaterThanOrEqual(switcherBox.x - 0.1);
      expect(box.y).toBeGreaterThanOrEqual(switcherBox.y - 0.1);
      expect(box.x + box.width).toBeLessThanOrEqual(switcherBox.x + switcherBox.width + 0.1);
      expect(box.y + box.height).toBeLessThanOrEqual(switcherBox.y + switcherBox.height + 0.1);
      expect(await button.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
      const pill = button.locator('[data-space-pill]');
      const pillBox = await pill.boundingBox();
      expect(pillBox.height).toBe(width < 1024 ? 28 : 44);
      expect(pillBox.y - trackBox.y).toBeCloseTo(gutter, 1);
      expect(trackBox.y + trackBox.height - pillBox.y - pillBox.height).toBeCloseTo(gutter, 1);
      const pillRadius = await pill.evaluate(element => parseFloat(getComputedStyle(element).borderTopLeftRadius));
      expect(effectiveTrackRadius - Math.min(pillRadius, pillBox.height / 2, pillBox.width / 2)).toBeCloseTo(gutter, 1);
    }
    await assertFits(page);
    await page.screenshot({ path: testInfo.outputPath(`family-${width}.png`), fullPage: true });
    await page.locator('[data-journal-sticky-header="true"]').screenshot({ path: testInfo.outputPath(`header-${width}.png`) });
    await visibleNav(page, width).getByRole('link', { name: 'Children', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Children', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Abby', exact: true })).toBeVisible();
    await expect(page.getByText('First drawing', { exact: true })).toBeVisible();
    const personalBoundary = reads.length;
    await personal.click({ position: { x: (await personal.boundingBox()).width / 2, y: 1 } });
    await expect(personal).toHaveAttribute('aria-pressed', 'true');
    await assertNavigation(page, width, PERSONAL_NAV);
    await expect(page.getByText('Read after breakfast', { exact: true }).first()).toBeVisible();
    await expect.poll(() => reads.some((read) => read.path === '/api/dashboard/' && read.space === 'personal')).toBe(true);
    await personal.focus();
    await page.keyboard.press('Shift+Tab');
    await expect(family).toBeFocused();
    const outline = await family.evaluate(button => {
      const style = getComputedStyle(button);
      return { visible: button.matches(':focus-visible'), width: parseFloat(style.outlineWidth),
        offset: parseFloat(style.outlineOffset), style: style.outlineStyle };
    });
    expect(outline.visible).toBe(true);
    expect(outline.width).toBeGreaterThan(0);
    expect(outline.style).not.toBe('none');
    expect(outline.style).not.toBe('hidden');
    const [familyBox, personalBox] = await Promise.all([family.boundingBox(), personal.boundingBox()]);
    expect(personalBox.x - familyBox.x - familyBox.width).toBeCloseTo(4, 1);
    expect(personalBox.x - familyBox.x - familyBox.width).toBeGreaterThanOrEqual(outline.width + outline.offset - 0.1);
    await assertFits(page);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('auth:last-user')).user.role)).toBe('parent');
    await page.screenshot({ path: testInfo.outputPath(`my-space-${width}.png`), fullPage: true });
    await page.goto(`${origin}/quests?tab=rituals`);
    await expect(page.getByRole('button', { name: 'New habit', exact: true })).toBeVisible();
    await expect.poll(() => reads.some((read) => read.path === '/api/habits/' && read.space === 'personal')).toBe(true);
    await page.getByRole('button', { name: 'New habit', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'New habit', exact: true });
    await expect(dialog.getByLabel('Child', { exact: true })).toHaveCount(0);
    await dialog.getByLabel('Name', { exact: true }).fill('Walk after lunch');
    await assertFits(page);
    await expect(family).toBeDisabled();
    await expect(page.getByText('Save or close your current form before switching spaces.')).toBeVisible();
    await dialog.getByRole('button', { name: 'Create habit', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(family).toBeEnabled();
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({ path: '/api/habits/', space: 'personal', body: { name: 'Walk after lunch', user: 6 } });
    expect(writes[0].body).not.toHaveProperty('user_id');
    for (const name of ['Pets', 'Rewards', 'Progress', 'Memories']) {
      await visibleNav(page, width).getByRole('link', { name, exact: true }).click();
      await expect(page.getByRole('tablist', { name: `${name} sections`, exact: true })).toBeVisible();
      await assertNavigation(page, width, PERSONAL_NAV);
      await assertFits(page);
    }
    const pendingReads = reads.slice(personalBoundary).filter((read) => read.query.status === 'pending');
    expect(pendingReads.length).toBeGreaterThan(0);
    expect(pendingReads.every((read) => read.space === undefined)).toBe(true);
    expect(reads.filter((read) => read.path !== '/api/sprites/catalog/').every(
      (read) => read.authorization === 'Token synthetic-parent-space-browser-session',
    )).toBe(true);
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`my-memories-${width}.png`), fullPage: true });
  });
  test(`child keeps six personal destinations without a switch at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const { errors, unexpected } = await mockApp(page, { child: true });
    await page.goto(`${origin}/`);
    await assertNavigation(page, width, PERSONAL_NAV);
    await expect(page.getByRole('group', { name: 'Choose your space' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('auth:last-user')).user.role)).toBe('child');
    await assertFits(page);
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`child-${width}.png`), fullPage: true });
  });
}

for (const width of [390, 1280]) {
  test(`parent project, milestone and chore receipts open saved personal content at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const receipts = [
      { id: 801, notification_type: 'project_approved', title: 'Project completed: Personal shelf',
        link: '/projects/917?space=personal', is_read: true },
      { id: 802, notification_type: 'milestone_completed', title: 'Milestone completed: Assemble shelf',
        link: '/projects/917?space=personal', is_read: true },
      { id: 803, notification_type: 'chore_approved', title: 'Chore completed: My personal chore',
        link: '/chores?space=personal', is_read: true },
    ];
    const { reads, errors, unexpected } = await mockApp(page, { notifications: receipts });
    await page.goto(`${origin}/`);
    const family = page.locator('button[aria-pressed]').filter({ hasText: /^Family/ });
    const personal = page.getByRole('button', { name: 'My space', exact: true });
    for (const receipt of receipts) {
      await expect(family).toHaveAttribute('aria-pressed', 'true');
      await page.getByRole('button', { name: 'Notifications', exact: true }).click();
      await page.getByRole('button', { name: receipt.title, exact: true }).click();
      const project = receipt.notification_type !== 'chore_approved';
      const canonical = project ? '/quests/ventures/917' : '/quests?tab=duties';
      const ownTitle = project ? fixtures['parent-personal-project-rate-default'].title : 'My personal chore';
      await expect(personal).toHaveAttribute('aria-pressed', 'true');
      await expect(page).toHaveURL(`${origin}${canonical}`);
      await expect(page.getByText(ownTitle, { exact: true }).first()).toBeVisible();
      await expect.poll(() => reads.some(read => read.path === (project ? '/api/projects/917/' : '/api/chores/')
        && read.space === 'personal')).toBe(true);
      if (receipt.notification_type === 'project_approved') {
        await page.getByRole('button', { name: 'Edit', exact: true }).click();
        const edit = page.getByRole('dialog', { name: 'Edit Project', exact: true });
        await expect(edit.getByText('Saving in My space sets hourly pay and the project cash bonus to zero.', { exact: false })).toBeVisible();
        await assertFits(page);
        await edit.getByRole('button', { name: 'Cancel', exact: true }).click();
        await expect(edit).toHaveCount(0);
      }
      await page.reload();
      await expect(personal).toHaveAttribute('aria-pressed', 'true');
      await expect(page.getByText(ownTitle, { exact: true }).first()).toBeVisible();
      await family.click();
    }
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
  });

  for (const launchSpace of ['personal', 'family']) {
    test(`parent keeps the chosen space after Back and reload from a ${launchSpace} link at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      const { reads, errors, unexpected } = await mockApp(page);
      const launchPath = launchSpace === 'personal' ? '/quests?space=personal'
        : '/chronicle?tab=journal&child=7&space=family';
      await page.goto(`${origin}${launchPath}`);
      const family = page.locator('button[aria-pressed]').filter({ hasText: /^Family/ });
      const personal = page.getByRole('button', { name: 'My space', exact: true });
      const initialButton = launchSpace === 'personal' ? personal : family;
      const chosenButton = launchSpace === 'personal' ? family : personal;
      await expect(initialButton).toHaveAttribute('aria-pressed', 'true');
      await expect.poll(() => new URL(page.url()).searchParams.get('space')).toBeNull();
      if (launchSpace === 'family') {
        expect(new URL(page.url()).searchParams.get('tab')).toBe('journal');
        expect(new URL(page.url()).searchParams.get('child')).toBe('7');
      }
      // Keep the launch page in real browser history, then replace the next
      // entry by deliberately choosing the other space.
      await visibleNav(page, width).getByRole('link', {
        name: launchSpace === 'personal' ? 'Progress' : 'Rewards', exact: true,
      }).click();
      await chosenButton.click();
      await expect(chosenButton).toHaveAttribute('aria-pressed', 'true');
      await page.goBack();
      await expect(page).toHaveURL(launchSpace === 'personal' ? `${origin}/quests`
        : `${origin}/chronicle?tab=journal&child=7`);
      await expect(chosenButton).toHaveAttribute('aria-pressed', 'true');
      await page.reload();
      await expect(chosenButton).toHaveAttribute('aria-pressed', 'true');
      const boundary = reads.length;
      await visibleNav(page, width).getByRole('link', { name: 'Today', exact: true }).click();
      await expect.poll(() => reads.slice(boundary).some(read => read.path === '/api/dashboard/'
        && read.space === (launchSpace === 'personal' ? undefined : 'personal'))).toBe(true);
      if (launchSpace === 'family') {
        // Router decodes this Family route. It must never become the saved
        // personal destination or make the My space button bounce to Family.
        await page.goto(`${origin}/%66amily?child=7`);
        await expect(family).toHaveAttribute('aria-pressed', 'true');
        await expect(page.getByRole('heading', { name: 'Abby', exact: true })).toBeVisible();
        await personal.click();
        await expect(personal).toHaveAttribute('aria-pressed', 'true');
        await page.reload();
        await expect(personal).toHaveAttribute('aria-pressed', 'true');
      }
      expect(await page.evaluate(() => JSON.parse(localStorage.getItem('auth:last-user')).user.role)).toBe('parent');
      expect(errors).toEqual([]);
      expect(unexpected).toEqual([]);
    });
  }
}
