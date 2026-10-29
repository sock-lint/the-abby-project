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

async function mockApp(page, { child = false, notifications = [], attentionCount = 0, recognition = false, timer = false, reviewState = 'ready' } = {}) {
  const reads = [];
  const writes = [];
  const errors = [];
  const unexpected = [];
  let releaseReviews = () => {};
  const reviewGate = reviewState === 'loading' ? new Promise(resolve => { releaseReviews = resolve; }) : Promise.resolve();
  const identity = fixtures[child ? 'auth-me-child' : 'auth-me-ordinary-parent'];
  const basePersonal = fixtures['parent-personal-dashboard'];
  const personal = recognition ? { ...basePersonal, rpg: { ...basePersonal.rpg, identity: {
    ...fixtures['dashboard-earned-identity'].rpg.identity, id: identity.id,
    username: identity.username, display_name: identity.display_name, avatar: null,
  } } } : basePersonal;
  const family = attentionCount ? { ...fixtures['parent-family-overview'], pending_timecards: attentionCount }
    : fixtures['parent-family-overview'];
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
    if (url.pathname === '/api/dashboard/') {
      if (!child && record.space !== 'personal') await reviewGate;
      return route.fulfill({ json: child ? fixtures['dashboard-earned-identity']
        : record.space === 'personal' ? personal : family });
    }
    if (reviewState === 'unavailable' && url.pathname === '/api/homework/dashboard/') {
      return route.fulfill({ status: 500, json: { error: 'Synthetic review source unavailable' } });
    }
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
        ...(recognition ? { identity: personal.rpg.identity } : {}),
        companion_growth: { events: [] }, expeditions_ready: [], savings_goals: [],
        header: { active_timer: timer ? { id: 991, project_title: 'Synthetic active project', elapsed_minutes: 65 } : null,
          coin_balance: 35, streak_days: 0, identity: personal.rpg.identity } },
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
  return { reads, writes, errors, unexpected, releaseReviews };
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

function spaceGroup(page, width) {
  return page.locator(`[data-space-switcher="${width < 1024 ? 'mobile' : 'desktop'}"]`);
}

async function assertContained(inner, outer) {
  const [child, parent] = await Promise.all([inner.boundingBox(), outer.boundingBox()]);
  expect(child.x).toBeGreaterThanOrEqual(parent.x - 0.5);
  expect(child.y).toBeGreaterThanOrEqual(parent.y - 0.5);
  expect(child.x + child.width).toBeLessThanOrEqual(parent.x + parent.width + 0.5);
  expect(child.y + child.height).toBeLessThanOrEqual(parent.y + parent.height + 0.5);
}

async function assertFullSpaceLabel(control) {
  const label = control.locator('span').first();
  const size = await label.evaluate(element => ({
    width: element.clientWidth, contentWidth: element.scrollWidth,
    height: element.clientHeight, contentHeight: element.scrollHeight,
  }));
  expect(size.contentWidth).toBeLessThanOrEqual(size.width + 1);
  expect(size.contentHeight).toBeLessThanOrEqual(size.height + 1);
}

function spaceControl(page, width, space = 'family') {
  return width < 1024 ? page.getByRole('combobox', { name: 'Choose your space' })
    : page.getByRole('button', { name: space === 'personal' ? 'My space' : /^Family/ });
}
async function assertSpace(page, width, space) {
  const control = spaceControl(page, width, space);
  if (width < 1024) await expect(control).toHaveAttribute('value', space);
  else await expect(control).toHaveAttribute('aria-pressed', 'true');
}
async function chooseSpace(page, width, space, edge = false) {
  const control = spaceControl(page, width, space);
  await control.click(edge ? { position: { x: (await control.boundingBox()).width / 2, y: 1 } } : {});
  if (width < 1024) {
    const listbox = page.getByRole('listbox', { name: 'Choose your space' });
    await expect(listbox.getByRole('option')).toHaveCount(2);
    for (const option of await listbox.getByRole('option').all()) {
      expect((await option.boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
    const menu = await listbox.boundingBox();
    expect(menu.x).toBeGreaterThanOrEqual(0);
    expect(menu.x + menu.width).toBeLessThanOrEqual(width);
    await listbox.getByRole('option', { name: space === 'personal' ? 'My space' : /^Family/ }).click();
    await expect(page.getByRole('listbox')).toHaveCount(0);
  }
}
async function assertFocusOutline(control) {
  const outline = await control.evaluate(element => {
    const style = getComputedStyle(element);
    return { visible: element.matches(':focus-visible'), width: parseFloat(style.outlineWidth),
      offset: parseFloat(style.outlineOffset), style: style.outlineStyle };
  });
  expect(outline.visible).toBe(true);
  expect(outline.width).toBeGreaterThan(0);
  expect(outline.style).not.toBe('none');
  expect(outline.style).not.toBe('hidden');
  return outline;
}

for (const width of [320, 390, 1280]) {
  test(`parent switches between Family and own full experience at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const { reads, writes, errors, unexpected } = await mockApp(page);
    await page.goto(`${origin}/`);
    const family = spaceControl(page, width, 'family');
    const personal = spaceControl(page, width, 'personal');
    await assertSpace(page, width, 'family');
    await assertNavigation(page, width, FAMILY_NAV);
    await expect(page.getByRole('heading', { name: 'Family overview' })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const switcher = spaceGroup(page, width);
    if (width >= 1024) await expect(switcher.getByRole('button')).toHaveCount(2);
    const track = switcher.locator('[data-space-track]');
    await expect(track).toHaveCount(1);
    const switcherBox = await switcher.boundingBox();
    const trackBox = await track.boundingBox();
    const rowBox = width >= 1024 ? await switcher.locator('..').boundingBox() : null;
    if (width < 1024) {
      await expect(page.locator('header').getByRole('combobox', { name: 'Choose your space' })).toHaveCount(1);
      await assertContained(personal, switcher);
      expect(trackBox.width).toBe(112);
      expect(trackBox.height).toBe(24);
      expect(switcherBox.height).toBe(44);
      const header = page.locator('[data-journal-sticky-header="true"] > header');
      expect((await header.boundingBox()).height).toBe(72);
      const controls = [header.locator('.identity-header__account'), switcher,
        header.getByRole('group', { name: 'Status shortcuts' }), header.getByRole('button', { name: 'Notifications', exact: true })];
      const boxes = await Promise.all(controls.map(control => control.boundingBox()));
      for (let i = 1; i < boxes.length; i++) {
        expect(boxes[i].x).toBeGreaterThanOrEqual(boxes[i - 1].x + boxes[i - 1].width);
        expect(boxes[i].y + boxes[i].height / 2).toBeCloseTo(boxes[0].y + boxes[0].height / 2, 0);
      }
      expect((await personal.boundingBox()).height).toBeGreaterThanOrEqual(44);
      expect(await personal.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
    } else {
      expect(trackBox.width).toBe(448);
      expect(trackBox.height).toBe(52);
      expect(rowBox.height).toBe(64);
    }
    const gutter = 4;
    const trackRadius = await track.evaluate(element => parseFloat(getComputedStyle(element).borderTopLeftRadius));
    const effectiveTrackRadius = Math.min(trackRadius, trackBox.height / 2, trackBox.width / 2);
    for (const button of width >= 1024 ? await switcher.getByRole('button').all() : []) {
      const box = await button.boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.x).toBeGreaterThanOrEqual(switcherBox.x - 0.1);
      expect(box.y).toBeGreaterThanOrEqual(switcherBox.y - 0.1);
      expect(box.x + box.width).toBeLessThanOrEqual(switcherBox.x + switcherBox.width + 0.1);
      expect(box.y + box.height).toBeLessThanOrEqual(switcherBox.y + switcherBox.height + 0.1);
      expect(await button.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
      const pill = button.locator('[data-space-pill]');
      const pillBox = await pill.boundingBox();
      expect(pillBox.height).toBe(44);
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
    await chooseSpace(page, width, 'personal', true);
    await assertSpace(page, width, 'personal');
    await assertNavigation(page, width, PERSONAL_NAV);
    await expect(page.getByText('Read after breakfast', { exact: true }).first()).toBeVisible();
    await expect.poll(() => reads.some((read) => read.path === '/api/dashboard/' && read.space === 'personal')).toBe(true);
    await personal.focus();
    if (width < 1024) {
      await page.keyboard.press('Tab');
      await page.keyboard.press('Shift+Tab');
      await expect(personal).toBeFocused();
      await assertFocusOutline(personal);
      await page.keyboard.press('ArrowDown');
      await expect(page.getByRole('listbox')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('listbox')).toHaveCount(0);
      await expect(personal).toBeFocused();
    } else {
      await page.keyboard.press('Shift+Tab');
      await expect(family).toBeFocused();
      const outline = await assertFocusOutline(family);
      const [familyBox, personalBox] = await Promise.all([family.boundingBox(), personal.boundingBox()]);
      expect(personalBox.x - familyBox.x - familyBox.width).toBeCloseTo(4, 1);
      expect(personalBox.x - familyBox.x - familyBox.width).toBeGreaterThanOrEqual(outline.width + outline.offset - 0.1);
    }
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
    await expect(page.locator('p:visible').filter({ hasText: 'Save or close your current form before switching spaces.' })).toBeVisible();
    await expect(family).toHaveAccessibleDescription('Save or close your current form before switching spaces.');
    if (width < 1024) {
      await expect(family).toHaveAttribute('aria-disabled', 'true');
    }
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
    await expect(page.locator('[data-space-switcher]')).toHaveCount(0);
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
    for (const receipt of receipts) {
      await assertSpace(page, width, 'family');
      await page.getByRole('button', { name: 'Notifications', exact: true }).click();
      await page.getByRole('button', { name: receipt.title, exact: true }).click();
      const project = receipt.notification_type !== 'chore_approved';
      const canonical = project ? '/quests/ventures/917' : '/quests?tab=duties';
      const ownTitle = project ? fixtures['parent-personal-project-rate-default'].title : 'My personal chore';
      await assertSpace(page, width, 'personal');
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
      await assertSpace(page, width, 'personal');
      await expect(page.getByText(ownTitle, { exact: true }).first()).toBeVisible();
      await chooseSpace(page, width, 'family');
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
      const chosenSpace = launchSpace === 'personal' ? 'family' : 'personal';
      await assertSpace(page, width, launchSpace);
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
      await expect(page.getByRole('tablist', { name: `${launchSpace === 'personal' ? 'Progress' : 'Rewards'} sections`, exact: true })).toBeVisible();
      await chooseSpace(page, width, chosenSpace);
      await assertSpace(page, width, chosenSpace);
      await page.goBack();
      await expect(page).toHaveURL(launchSpace === 'personal' ? `${origin}/quests`
        : `${origin}/chronicle?tab=journal&child=7`);
      await assertSpace(page, width, chosenSpace);
      await page.reload();
      await assertSpace(page, width, chosenSpace);
      const boundary = reads.length;
      await visibleNav(page, width).getByRole('link', { name: 'Today', exact: true }).click();
      await expect.poll(() => reads.slice(boundary).some(read => read.path === '/api/dashboard/'
        && read.space === (launchSpace === 'personal' ? undefined : 'personal'))).toBe(true);
      if (launchSpace === 'family') {
        // Router decodes this Family route. It must never become the saved
        // personal destination or make the My space button bounce to Family.
        await page.goto(`${origin}/%66amily?child=7`);
        await assertSpace(page, width, 'family');
        await expect(page.getByRole('heading', { name: 'Abby', exact: true })).toBeVisible();
        await chooseSpace(page, width, 'personal');
        await assertSpace(page, width, 'personal');
        await page.reload();
        await assertSpace(page, width, 'personal');
      }
      expect(await page.evaluate(() => JSON.parse(localStorage.getItem('auth:last-user')).user.role)).toBe('parent');
      expect(errors).toEqual([]);
      expect(unexpected).toEqual([]);
    });
  }
}

for (const width of [320, 390, 820]) {
  for (const enlarged of [false, true]) {
    test(`parent header controls stay reachable at ${width}px with ${enlarged ? '200%' : 'normal'} text`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      const notice = { id: 991, notification_type: 'project_approved', title: 'Synthetic header notice',
        link: '/projects/917?space=personal', is_read: true };
      const { errors, unexpected } = await mockApp(page, {
        attentionCount: 12, recognition: true, timer: true, notifications: [notice],
      });
      await page.goto(`${origin}/`);
      const control = page.getByRole('combobox', { name: 'Choose your space' });
      await expect(control).toHaveText(/Family 9\+/);
      await expect(control).toHaveAccessibleDescription('12 family items needing attention');
      await expect(page.getByRole('heading', { name: 'Family overview' })).toBeVisible();
      await expect(page.getByRole('group', { name: 'Choose your space' })).toHaveCount(0);
      await page.evaluate(() => document.fonts.ready);
      if (enlarged) {
        // Enlarge header text and its popovers without changing the viewport
        // or unrelated page cards. Confirm the trigger's actual size below.
        await page.evaluate(() => {
          const style = getComputedStyle(document.documentElement);
          const rules = [...style].filter(name => name.startsWith('--text-')).flatMap(name => {
            const match = style.getPropertyValue(name).trim().match(/^([\d.]+)(px|rem)$/);
            return match ? [`${name}: ${Number(match[1]) * 2}${match[2]}`] : [];
          });
          const sheet = document.createElement('style');
          sheet.textContent = `[data-journal-sticky-header], [role="listbox"], [role="dialog"] { ${rules.join(';')} }`;
          document.head.append(sheet);
        });
      }
      expect(await control.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBe(enlarged ? 28 : 14);
      await assertFullSpaceLabel(control);
      await assertContained(control, spaceGroup(page, width));
      await assertFits(page);
      const header = page.locator('[data-journal-sticky-header="true"] > header');
      expect(await header.ariaSnapshot()).not.toContain('- text: 12 family items needing attention');
      await header.screenshot({ path: testInfo.outputPath(`family-attention-${width}.png`) });
      const bell = header.getByRole('button', { name: 'Notifications', exact: true });
      const clock = header.getByRole('button', { name: 'Clocked in on Synthetic active project', exact: true });
      for (const target of [control, bell, clock]) {
        const box = await target.boundingBox();
        expect(box.height).toBeGreaterThanOrEqual(44);
        await target.focus();
        await expect(target).toBeFocused();
        await target.click({ trial: true });
      }
      // The compact header uses the existing horizontal shortcut rail. Every
      // shortcut must become fully reachable when keyboard focus reveals it.
      for (const shortcut of await header.getByRole('group', { name: 'Status shortcuts' }).getByRole('button').all()) {
        await shortcut.focus();
        await expect(shortcut).toBeFocused();
        await shortcut.click({ trial: true });
      }
      await control.focus();
      await control.press('ArrowDown');
      await expect(page.getByRole('listbox')).toBeVisible();
      await expect(page.getByRole('option', { name: 'Family 9+', exact: true })).toBeVisible();
      const menu = await page.getByRole('listbox').boundingBox();
      expect(menu.x).toBeGreaterThanOrEqual(0);
      expect(menu.x + menu.width).toBeLessThanOrEqual(width);
      await page.screenshot({ path: testInfo.outputPath(`space-menu-${width}.png`) });
      await control.press('Escape');
      await expect(page.getByRole('listbox')).toHaveCount(0);
      await expect(control).toBeFocused();
      await expect(control).toHaveAttribute('value', 'family');
      await control.press('Enter');
      await control.press('End');
      await control.press('Enter');
      await expect(control).toHaveAttribute('value', 'personal');
      await assertFullSpaceLabel(control);
      await assertContained(control, spaceGroup(page, width));
      await assertFits(page);
      await header.screenshot({ path: testInfo.outputPath(`personal-recognition-${width}.png`) });
      await header.getByRole('button', { name: 'Open profile menu', exact: true }).click();
      const profile = page.getByRole('menu', { name: 'Profile', exact: true });
      await expect(profile.getByText('Master Crafter', { exact: true })).toBeVisible();
      await expect(profile.getByText('Fixture maker', { exact: true })).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`profile-recognition-${width}.png`) });
      await page.keyboard.press('Escape');
      await expect(profile).toHaveCount(0);
      await bell.click();
      const notifications = page.getByRole(width < 768 ? 'dialog' : 'region', { name: 'Notifications', exact: true });
      await expect(notifications).toBeVisible();
      await expect(notifications.getByRole('button', { name: notice.title, exact: true })).toBeVisible();
      if (width < 768) await notifications.getByRole('button', { name: 'Close', exact: true }).click();
      else await bell.click();
      await expect(notifications).toHaveCount(0);
      await clock.focus();
      await clock.click();
      await expect(page).toHaveURL(`${origin}/clock`);
      await assertFits(page);
      expect(errors).toEqual([]);
      expect(unexpected).toEqual([]);
    });
  }
}

// Exercise touch events in WebKit itself: mouse clicks in a narrow viewport
// do not reproduce WebKit's handling of canceled touch pointer events.
test.describe('WebKit touch space switching', () => {
  for (const width of [320, 390, 820]) {
    test(`touch input switches both spaces at ${width}px`, async ({ playwright }) => {
      const browser = await playwright.webkit.launch();
      try {
        const page = await browser.newPage({ viewport: { width, height: 844 }, hasTouch: true, isMobile: true });
        const { reads, writes, errors, unexpected } = await mockApp(page);
        await page.goto(`${origin}/`);
        const control = spaceControl(page, width);
        await assertSpace(page, width, 'family');
        for (const space of ['personal', 'family']) {
          await control.tap();
          const option = page.getByRole('option', { name: space === 'personal' ? 'My space' : /^Family/, exact: true });
          await option.tap();
          await expect(page.getByRole('listbox')).toHaveCount(0);
          await assertSpace(page, width, space);
          await assertNavigation(page, width, space === 'personal' ? PERSONAL_NAV : FAMILY_NAV);
        }
        expect(reads.some(read => read.path === '/api/dashboard/' && read.space === 'personal')).toBe(true);
        expect(writes).toEqual([]);
        expect(errors).toEqual([]);
        expect(unexpected).toEqual([]);
      } finally {
        await browser.close();
      }
    });
  }
});

for (const width of [390, 1280]) {
  test(`unfinished page form keeps switch help reachable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const { writes, errors, unexpected } = await mockApp(page);
    await page.goto(`${origin}/quests/ventures/new`);
    const title = page.getByLabel('Title', { exact: true });
    await title.fill('Keep this unfinished project');
    const help = 'Save or close your current form before switching spaces.';
    const control = spaceControl(page, width, 'personal');
    await expect(control).toBeDisabled();
    await expect(control).toHaveAccessibleDescription(help);
    if (width < 1024) {
      await page.getByRole('button', { name: 'Open profile menu', exact: true }).focus();
      await page.keyboard.press('Tab');
      await expect(control).toBeFocused();
      await control.press('Enter');
      await control.press('ArrowDown');
      await control.click({ force: true });
      await expect(page.getByRole('listbox')).toHaveCount(0);
    } else {
      await expect(spaceControl(page, width, 'family')).toHaveAccessibleDescription(help);
    }
    await assertSpace(page, width, 'family');
    await expect(title).toHaveValue('Keep this unfinished project');
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
  });
}

for (const reviewState of ['loading', 'unavailable']) {
  test(`compact switch exposes ${reviewState} family reviews`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const { releaseReviews, errors, unexpected } = await mockApp(page, { reviewState });
    await page.goto(`${origin}/`);
    const control = spaceControl(page, 390);
    try {
      await expect(control).toHaveText(reviewState === 'loading' ? 'Family …' : 'Family ?');
      await expect(control).toHaveAccessibleDescription(reviewState === 'loading'
        ? 'Checking family reviews' : 'Some family review queues are unavailable');
      await control.click();
      await expect(page.getByRole('option', { name: reviewState === 'loading' ? 'Family …' : 'Family ?', exact: true })).toBeVisible();
      await control.press('Escape');
    } finally {
      releaseReviews();
    }
    if (reviewState === 'loading') {
      await expect(page.getByRole('heading', { name: 'Family overview' })).toBeVisible();
      await expect(control).toHaveText('Family');
    }
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
  });
}

for (const child of [false, true]) {
  test(`tablet header preserves ${child ? 'child name' : 'compact parent identity'} at 820px`, async ({ page }) => {
    await page.setViewportSize({ width: 820, height: 844 });
    const { errors, unexpected } = await mockApp(page, { child });
    await page.goto(`${origin}/`);
    await assertNavigation(page, 820, child ? PERSONAL_NAV : FAMILY_NAV);
    const copy = page.locator('header .identity-header__account .identity-summary__copy');
    if (child) {
      await expect(copy).toBeVisible();
      await expect(copy.locator('.identity-summary__name')).toHaveText(fixtures['auth-me-child'].display_name);
      await expect(page.locator('[data-space-switcher]')).toHaveCount(0);
    } else await expect(copy).toBeHidden();
    expect(errors).toEqual([]);
    expect(unexpected).toEqual([]);
  });
}

test('desktop header follows its visual keyboard order without duplicate attention text', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 844 });
  const { errors, unexpected } = await mockApp(page, { attentionCount: 12, recognition: true, timer: true });
  await page.goto(`${origin}/`);
  const header = page.locator('[data-journal-sticky-header="true"] > header');
  const profile = header.getByRole('button', { name: 'Open profile menu', exact: true });
  await expect(spaceControl(page, 1280)).toHaveText(/Family\s*9\+/);
  const shortcuts = await header.getByRole('group', { name: 'Status shortcuts' }).getByRole('button').all();
  const targets = [profile, ...shortcuts, header.getByRole('button', { name: 'Notifications', exact: true }),
    spaceControl(page, 1280, 'family'), spaceControl(page, 1280, 'personal')];
  await profile.focus();
  for (const target of targets.slice(1)) {
    await page.keyboard.press('Tab');
    await expect(target).toBeFocused();
  }
  for (const target of targets.slice(0, -1).reverse()) {
    await page.keyboard.press('Shift+Tab');
    await expect(target).toBeFocused();
  }
  expect((await header.boundingBox()).height).toBe(144);
  expect((await spaceGroup(page, 1280).locator('..').boundingBox()).height).toBe(64);
  expect(await header.ariaSnapshot()).not.toContain('- text: 12 family items needing attention');
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});

test('zoomed narrow header keeps profile, space, clock and notifications reachable', async ({ page }) => {
  await page.setViewportSize({ width: 195, height: 422 });
  const { errors, unexpected } = await mockApp(page, { attentionCount: 12, timer: true });
  await page.goto(`${origin}/`);
  const header = page.locator('[data-journal-sticky-header="true"] > header');
  const targets = [header.getByRole('button', { name: 'Open profile menu', exact: true }), spaceControl(page, 195),
    header.getByRole('button', { name: 'Clocked in on Synthetic active project', exact: true }),
    header.getByRole('button', { name: 'Notifications', exact: true })];
  for (const target of targets) {
    await target.focus();
    await expect(target).toBeFocused();
    const box = await target.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(195);
    expect(await target.evaluate(element => {
      const rect = element.getBoundingClientRect();
      return element.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
    })).toBe(true);
  }
  await assertContained(spaceControl(page, 195), spaceGroup(page, 195));
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});
