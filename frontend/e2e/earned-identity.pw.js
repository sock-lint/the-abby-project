import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { isAbsolute, join } from 'node:path';
import { stripVTControlCharacters } from 'node:util';

const profileFixture = JSON.parse(readFileSync(new URL('../../contracts/api/fixtures/character-avatar-default.json', import.meta.url), 'utf8'));
const frames = [
  ['bronze', 'Bronze Frame'], ['silver', 'Silver Frame'], ['gold', 'Gold Frame'], ['cosmic', 'Cosmic Frame'],
  ['barbute', 'Barbute Helm Frame'], ['robin-hood', "Ranger's Cap Frame"], ['cross-helm', 'Paladin Helm Frame'],
  ['scholar', 'Scholar Frame'], ['laurel', 'Laurel Wreath Frame'], ['rune-circle', 'Rune Circle Frame'],
  ['steampunk', 'Steampunk Gear Frame'], ['pixel', 'Pixel Pixel Frame'], ['high-school-trophy', 'High School Trophy Frame'],
  ['moonlit', 'Moonlit Frame'], ['confetti', 'Confetti Frame'], ['seashell', 'Seashell Frame'],
  ['chronicle', 'Chronicle Frame'], ['far-horizons', 'Far Horizons Frame'],
].map(([family, name], index) => ({ id: 100 + index, slug: `frame-${family}`, name, item_type: 'cosmetic_frame', rarity: 'rare', metadata: {} }));
const title = { id: 201, slug: 'title-master-crafter', name: 'Master Crafter', item_type: 'cosmetic_title', icon: '🛠️', catalog_icon: 'item-title-master-crafter', rarity: 'rare', metadata: { text: 'Master Crafter' } };
const badge = { id: 301, name: 'First Project', icon: '🏅', catalog_icon: 'badge-first-project', rarity: 'common', description: 'Finished your first project.' };
const privateArtworkInstalled = ['abby-catalog-icons', 'abby-artwork-completion', 'abby-portrait-frame-kit']
  .every((family) => existsSync(new URL(`../src/avatar/shared/${family}/`, import.meta.url)));
const captureDirectory = process.env.ABBY_EARNED_IDENTITY_CAPTURE_DIR;
let devServer;
let origin;

test.use({ trace: 'off', video: 'off', screenshot: 'off', actionTimeout: 15_000 });

test.beforeAll(async () => {
  // Run the actual application against intercepted, synthetic API state only.
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Identity fixture startup timed out: ${output}`)), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Identity fixture exited (${code}): ${output}`)); });
    devServer.stderr.on('data', (chunk) => { output += chunk.toString(); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
  if (captureDirectory) {
    if (!isAbsolute(captureDirectory)) throw new Error('Identity captures require an absolute private output directory.');
    await mkdir(captureDirectory, { recursive: true });
  }
});

test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

async function fixture(page, { parent = false, longNames = false, failedAvatar = false, busy = false,
  selectedTitle = title, selectedBadge = badge, frameFamily = 'laurel' } = {}) {
  const user = {
    id: parent ? 902 : 901, username: parent ? 'synthetic-parent' : 'synthetic-maker', role: parent ? 'parent' : 'child',
    display_name: parent ? 'Sam Parent' : longNames ? 'Alexandria Verylongfamilyname The Enthusiastic Maker' : 'Alex Maker',
    avatar: failedAvatar ? `${origin}/synthetic-avatar-missing.png` : null, theme: 'hyrule',
    family: { id: 90, name: 'Synthetic Family', timezone: 'America/Phoenix' },
  };
  let identity = { id: user.id, username: user.username, display_name: user.display_name, avatar: user.avatar,
    active_frame: frames.find((frame) => frame.slug === `frame-${frameFamily}`),
    active_title: longNames ? { ...selectedTitle, metadata: { text: 'Extraordinarily Thoughtful Maker of Wonderful Things' } } : selectedTitle,
    active_trophy_badge: selectedBadge };
  let maker = parent ? { ...identity, id: 901, username: 'synthetic-maker', display_name: 'Alex Maker', avatar: null,
    active_frame: frames.find((frame) => frame.slug === 'frame-steampunk'), active_title: selectedTitle } : identity;
  const mutations = [];
  let holdSave;
  let releaseSave;
  let pulseReads = 0;
  await page.addInitScript(() => {
    localStorage.setItem('abby_auth_token', 'synthetic-earned-identity-session');
    localStorage.setItem('avatar_hint_count', '3');
  });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/synthetic-avatar-missing.png') return route.fulfill({ status: 404, body: '' });
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (request.method() !== 'GET') {
      const body = request.postDataJSON();
      mutations.push({ path: url.pathname, method: request.method(), body });
      if (url.pathname === '/api/character/equip/' && request.method() === 'POST') {
        const frame = frames.find((entry) => entry.id === body.item_id);
        if (!frame) return reply({ error: 'Unknown synthetic frame.' }, 400);
        if (holdSave) await holdSave;
        identity = { ...identity, active_frame: frame };
        if (!parent) maker = identity;
        return reply({ ...profileFixture, ...identity });
      }
      return reply({ error: 'Unexpected mutation in read-only identity fixture.' }, 400);
    }
    if (url.pathname.includes('pending-celebration')) return route.fulfill({ status: 204 });
    // The identity acceptance suite does not need a GPU or private 3D avatar.
    const profile = { ...profileFixture, ...identity, level: 3,
      avatar_configuration: { avatar_id: 'synthetic-unprepared', appearance: {}, accessories: {} } };
    const responses = {
      '/api/auth/me/': user,
      '/api/pulse/': { unread_count: 0, notifications: [], recent_drops: [], active_quest: null, companion_growth: { events: [] },
        expeditions_ready: [], savings_goals: [], newly_unlocked_lorebook: [], identity,
        header: { active_timer: busy ? { project_title: 'Synthetic next task', elapsed_minutes: 165 } : null,
          coin_balance: busy ? 999999 : 197, streak_days: busy ? 365 : 4, level: 3 } },
      '/api/dashboard/': { active_timer: null, current_balance: '0.00', coin_balance: 197, this_week: {}, active_projects: [],
        recent_badges: [], savings_goals: [], next_actions: [], rpg: { ...profile, identity } },
      '/api/character/': profile,
      '/api/character/avatar/catalog/': { default_avatar_id: 'synthetic-unprepared', avatars: [] },
      '/api/cosmetics/': { active_frame: frames, active_title: [selectedTitle] },
      '/api/cosmetics/catalog/': { active_frame: frames, active_title: [selectedTitle] },
      '/api/badges/': [selectedBadge], '/api/achievements/summary/': { badges_earned: [selectedBadge] },
      '/api/challenges/': { results: [], pin: null, daily_bonus: null },
      '/api/sprites/catalog/': { sprites: {} }, '/api/push/config/': { enabled: false, public_key: '' },
      '/api/clock/': null, '/api/pets/stable/': { pets: [], mounts: [] }, '/api/coins/summary-by-day/': { series: [] },
      '/api/wellbeing/today/': {}, '/api/chronicle/today/': null,
      '/api/projects/77/': { id: 77, title: 'Build a Bird Feeder', description: 'A synthetic family project.', status: 'completed',
        completed_at: '2026-10-20T16:00:00Z', payment_kind: 'required', difficulty: 3, bonus_amount: '5.00', materials_budget: '12.00',
        xp_reward: 50, assigned_to: { id: 901, username: 'synthetic-maker', display_name: maker.display_name }, maker_signature: maker,
        milestones: [], steps: [], resources: [], materials: [], collaborators: [] },
    };
    if (url.pathname === '/api/pulse/') pulseReads += 1;
    return reply(responses[url.pathname] ?? []);
  });
  return {
    mutations, pulseReads: () => pulseReads,
    frame: (family) => { identity = { ...identity, active_frame: frames.find((frame) => frame.slug === `frame-${family}`) }; },
    holdNextSave: () => { holdSave = new Promise((resolve) => { releaseSave = resolve; }); },
    releaseSave: () => { releaseSave?.(); holdSave = undefined; },
  };
}

function profileTrigger(page) { return page.locator('[data-journal-sticky-header]').getByRole('button', { name: 'Open profile menu', exact: true }); }

function navigationIdentity(page) {
  return page.locator('[data-journal-sticky-header]');
}

async function levelBelowPortrait(scope) {
  const portrait = await scope.locator('[data-portrait-frame]').boundingBox();
  const level = scope.getByLabel('Level 3', { exact: true });
  await expect(level).toHaveText('Lv. 3');
  const dock = await level.boundingBox();
  expect(dock.y).toBeGreaterThanOrEqual(portrait.y + portrait.height / 2);
  expect(Math.abs(dock.x + dock.width / 2 - (portrait.x + portrait.width / 2))).toBeLessThanOrEqual(2);
}

async function savedArtwork(scope) {
  const titleIcon = scope.locator('.character-title__icon');
  const badgeChip = scope.getByText('First Project', { exact: true }).locator('..');
  return {
    title: await titleIcon.evaluate((element) => element.querySelector('img')?.getAttribute('src') || element.textContent),
    badge: await badgeChip.evaluate((element) => element.querySelector('img')?.getAttribute('src') || element.textContent),
  };
}

async function fitsViewport(page, locator) {
  const width = page.viewportSize().width;
  const bounds = await locator.boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(-1);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
  const contentWidth = await locator.evaluate((element) => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(contentWidth.scroll, `Content overflows its ${contentWidth.client}px container`).toBeLessThanOrEqual(contentWidth.client + 1);
}

async function showsFullText(locator) {
  await expect(locator).toBeVisible();
  expect(await locator.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const text = range.getBoundingClientRect();
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      const style = getComputedStyle(ancestor);
      const bounds = ancestor.getBoundingClientRect();
      if (/(hidden|clip|auto|scroll)/.test(style.overflowX) && (text.left < bounds.left - 1 || text.right > bounds.right + 1)) return false;
      if (/(hidden|clip|auto|scroll)/.test(style.overflowY) && (text.top < bounds.top - 1 || text.bottom > bounds.bottom + 1)) return false;
    }
    return element.scrollWidth <= element.clientWidth + 1 && text.left >= 0 && text.right <= window.innerWidth;
  })).toBe(true);
}

for (const width of [320, 375, 1280]) {
  test(`saved identity stays in navigation and project signatures while Today leads with tasks at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    const state = await fixture(page, { longNames: true, failedAvatar: true, busy: width === 375 });
    await page.goto(origin);
    await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'No urgent tasks right now', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Your look', exact: true })).toHaveCount(0);
    const trigger = profileTrigger(page);
    await expect(trigger.locator('[data-portrait-frame="laurel"]')).toBeVisible();
    await expect(trigger.locator('.profile-portrait__initial')).toHaveText('A');
    await expect(trigger.locator('.profile-portrait__image img')).toHaveCount(0);
    const navigation = navigationIdentity(page);
    await showsFullText(navigation.getByText('Extraordinarily Thoughtful Maker of Wonderful Things', { exact: true }));
    await showsFullText(navigation.getByText('First Project', { exact: true }));
    const artwork = await savedArtwork(navigation);
    await levelBelowPortrait(trigger);
    await expect(trigger).toContainText('Alexandria Verylongfamilyname');
    await expect(trigger).not.toContainText('Synthetic Family');
    if (width >= 1024) {
      const sidebar = page.locator('aside').getByRole('button', { name: 'Open profile menu', exact: true });
      await expect(sidebar).toContainText('Alexandria Verylongfamilyname');
      await expect(sidebar).toContainText('Synthetic Family');
      await expect(sidebar.getByText('First Project', { exact: true })).toBeVisible();
      await levelBelowPortrait(sidebar);
    }
    if (captureDirectory) await page.screenshot({ path: join(captureDirectory, `today-${width}.png`) });
    await fitsViewport(page, trigger);
    const target = await trigger.boundingBox();
    expect(target.width).toBeGreaterThanOrEqual(44);
    expect(target.height).toBeGreaterThanOrEqual(44);
    if (width === 375) expect(target.height, 'The compact account name must not turn the phone header into a tall column.').toBeLessThanOrEqual(80);
    await trigger.focus();
    await page.keyboard.press('ArrowDown');
    const menu = page.getByRole('menu', { name: 'Profile', exact: true });
    await expect(menu).toBeVisible();
    await expect(menu).toContainText('Alexandria Verylongfamilyname');
    await expect(menu).toContainText('Synthetic Family');
    await expect(menu.getByText('First Project', { exact: true })).toBeVisible();
    await levelBelowPortrait(menu);
    await showsFullText(menu.getByText('Extraordinarily Thoughtful Maker of Wonderful Things', { exact: true }));
    expect(await savedArtwork(menu)).toEqual(artwork);
    await expect(menu).toHaveCSS('transform', 'none');
    for (const item of await menu.getByRole('menuitem').all()) expect((await item.boundingBox()).height).toBeGreaterThanOrEqual(44);
    await expect(menu.getByRole('menuitem', { name: /Profile/ })).toBeFocused();
    if (captureDirectory) await page.screenshot({ path: join(captureDirectory, `menu-${width}.png`) });
    await page.keyboard.press('End');
    await expect(menu.getByRole('menuitem', { name: /Settings/ })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(trigger).toBeFocused();
    await expect(menu).toHaveCount(0);
    await page.goto(`${origin}/sigil`);
    const profile = page.locator('[data-identity-summary]').filter({ has: page.getByRole('heading', { name: 'Alexandria Verylongfamilyname The Enthusiastic Maker', exact: true }) });
    await showsFullText(profile.getByText('Extraordinarily Thoughtful Maker of Wonderful Things', { exact: true }));
    await showsFullText(profile.getByText('First Project', { exact: true }));
    await levelBelowPortrait(profile);
    expect(await savedArtwork(profile)).toEqual(artwork);
    await fitsViewport(page, profile);
    if (captureDirectory) await page.screenshot({ path: join(captureDirectory, `profile-${width}.png`) });
    await page.goto(`${origin}/quests/ventures/77`);
    const signature = page.getByRole('region', { name: 'Project maker', exact: true });
    await expect(signature).toContainText('Made by Alexandria Verylongfamilyname');
    await expect(signature).toContainText('First Project');
    await expect(signature.locator('[data-portrait-frame="laurel"]')).toBeVisible();
    await fitsViewport(page, signature);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(state.mutations).toEqual([]);
  });
}

test('saved identity remains readable with enlarged text and reduced motion on light and dark covers', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 850 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const state = await fixture(page, { longNames: true });
  await page.goto(`${origin}/sigil`);
  await page.addStyleTag({ content: ':root { font-size: 24px; }' });
  for (const theme of ['hyrule', 'vigil']) {
    await page.evaluate(async (name) => (await import('/src/themes.js')).applyTheme(name), theme);
    const header = navigationIdentity(page);
    await showsFullText(header.getByText('Extraordinarily Thoughtful Maker of Wonderful Things', { exact: true }));
    await showsFullText(header.getByText('First Project', { exact: true }));
    await levelBelowPortrait(profileTrigger(page));
    await profileTrigger(page).click();
    const menu = page.getByRole('menu', { name: 'Profile', exact: true });
    await showsFullText(menu.getByText('Extraordinarily Thoughtful Maker of Wonderful Things', { exact: true }));
    await showsFullText(menu.getByText('First Project', { exact: true }));
    await fitsViewport(page, menu);
    await page.keyboard.press('Escape');
    const profile = page.locator('[data-identity-summary]').filter({ has: page.getByRole('heading', { name: 'Alexandria Verylongfamilyname The Enthusiastic Maker', exact: true }) });
    await showsFullText(profile.getByText('Extraordinarily Thoughtful Maker of Wonderful Things', { exact: true }));
    await showsFullText(profile.getByText('First Project', { exact: true }));
    await fitsViewport(page, profile);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
  expect(state.mutations).toEqual([]);
});

test('the installed Chore Hero and First Dollar artwork matches in the header, menu and Profile', async ({ page }) => {
  test.skip(!privateArtworkInstalled, 'Private catalog, badge artwork and portrait frame imports are required for PNG acceptance; ordinary identity cases validate readable fallbacks.');
  await page.setViewportSize({ width: 375, height: 850 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const state = await fixture(page, {
    selectedTitle: { id: 202, slug: 'title-chore-hero', name: 'Chore Hero', item_type: 'cosmetic_title',
      icon: '🏆', catalog_icon: 'item-title-chore-hero', rarity: 'rare', metadata: { text: 'Chore Hero' } },
    selectedBadge: { id: 302, name: 'First Dollar', icon: '💰', catalog_icon: 'badge-first-dollar', rarity: 'common' },
    frameFamily: 'steampunk',
  });
  await page.goto(`${origin}/sigil`);
  async function loadedArtwork(scope) {
    await showsFullText(scope.getByText('Chore Hero', { exact: true }));
    await showsFullText(scope.getByText('First Dollar', { exact: true }));
    const images = [scope.locator('.character-title__icon img'), scope.locator('[data-artwork-image="badge-first-dollar"]')];
    const sources = [];
    for (const image of images) {
      await expect(image).toBeVisible();
      await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth)).toBe(256);
      const source = await image.getAttribute('src');
      expect(source).toMatch(/objects\/[a-f0-9]{64}\.png/);
      sources.push(source);
    }
    return sources;
  }
  const header = navigationIdentity(page);
  const artwork = await loadedArtwork(header);
  await expect(profileTrigger(page).locator('[data-portrait-overlay="item-frame-steampunk"]')).toBeVisible();
  await renderedFrame(profileTrigger(page).locator('[data-portrait-frame="steampunk"]'));
  const profile = page.locator('[data-identity-summary]').filter({ has: page.getByRole('heading', { name: 'Alex Maker', exact: true }) });
  expect(await loadedArtwork(profile)).toEqual(artwork);
  await expect(profile.locator('[data-portrait-overlay="item-frame-steampunk"]')).toBeVisible();
  await renderedFrame(profile.locator('[data-portrait-frame="steampunk"]'));
  await levelBelowPortrait(profile);
  if (captureDirectory) {
    await header.screenshot({ path: join(captureDirectory, 'requested-header-375.png') });
    await page.screenshot({ path: join(captureDirectory, 'requested-profile-375.png') });
  }
  await profileTrigger(page).click();
  const menu = page.getByRole('menu', { name: 'Profile', exact: true });
  expect(await loadedArtwork(menu)).toEqual(artwork);
  await expect(menu.locator('[data-portrait-overlay="item-frame-steampunk"]')).toBeVisible();
  await renderedFrame(menu.locator('[data-portrait-frame="steampunk"]'));
  await levelBelowPortrait(menu);
  if (captureDirectory) await page.screenshot({ path: join(captureDirectory, 'requested-menu-375.png') });
  expect(state.mutations).toEqual([]);
});

test('a parent sees the assigned maker identity rather than their own selection', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  const state = await fixture(page, { parent: true });
  await page.goto(`${origin}/quests/ventures/77`);
  await expect(profileTrigger(page)).toContainText('Sam Parent');
  await expect(profileTrigger(page).locator('[data-portrait-frame="laurel"]')).toBeVisible();
  await profileTrigger(page).click();
  const menu = page.getByRole('menu', { name: 'Profile', exact: true });
  await expect(menu.getByText('Sam Parent', { exact: true })).toBeVisible();
  await expect(menu.getByText('First Project', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  const signature = page.getByRole('region', { name: 'Project maker', exact: true });
  await expect(signature).toContainText('Made by Alex Maker');
  await expect(signature.locator('[data-portrait-frame="steampunk"]')).toBeVisible();
  await expect(signature).not.toContainText('Sam Parent');
  expect(state.mutations).toEqual([]);
});

test('a confirmed Profile frame selection refreshes navigation immediately and stays selected on Today', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  const state = await fixture(page);
  await page.goto(`${origin}/sigil`);
  const trigger = profileTrigger(page);
  await expect(trigger.locator('[data-portrait-frame="laurel"]')).toBeVisible();
  const before = state.pulseReads();
  state.holdNextSave();
  const equip = page.getByRole('button', { name: 'Steampunk Gear Frame · rare · click to equip', exact: true });
  await equip.click();
  await expect.poll(() => state.mutations.length).toBe(1);
  await expect(trigger.locator('[data-portrait-frame="laurel"]')).toBeVisible();
  state.releaseSave();
  await expect(trigger.locator('[data-portrait-frame="steampunk"]')).toBeVisible();
  await expect(navigationIdentity(page).getByText('Master Crafter', { exact: true })).toBeVisible();
  expect(state.pulseReads()).toBeGreaterThan(before);
  expect(state.mutations).toEqual([{ path: '/api/character/equip/', method: 'POST', body: { item_id: 110 } }]);
  await trigger.click();
  await expect(page.getByRole('menu', { name: 'Profile', exact: true }).getByText('First Project', { exact: true })).toBeVisible();
  await page.getByRole('menuitem', { name: /Profile/ }).press('Escape');
  await page.getByRole('link', { name: 'Today', exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Your look', exact: true })).toHaveCount(0);
  await expect(trigger.locator('[data-portrait-frame="steampunk"]')).toBeVisible();
  await expect(navigationIdentity(page).getByText('Master Crafter', { exact: true })).toBeVisible();
  expect(state.mutations).toHaveLength(1);
});

test('all authored frame silhouettes render at navigation and Profile sizes with a dark-theme fallback', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  const state = await fixture(page);
  const shapes = new Map([40, 96].map((size) => [size, new Set()]));
  const portraits = [];
  for (const frame of frames) {
    const family = frame.slug.slice('frame-'.length);
    state.frame(family);
    await page.goto(`${origin}/sigil`);
    const profile = page.getByRole('img', { name: `Your profile picture with ${frame.name}`, exact: true });
    const mobile = profileTrigger(page).locator(`[data-portrait-frame="${family}"]`);
    const examples = [[40, mobile], [96, profile]];
    const captured = { name: frame.name };
    for (const [size, portrait] of examples) {
      await expect(portrait).toBeVisible();
      await expect(portrait).toHaveCSS('width', `${size}px`);
      shapes.get(size).add(await renderedFrame(portrait));
      if (captureDirectory) captured[size] = await portrait.evaluate((element) => element.outerHTML);
    }
    await page.setViewportSize({ width: 1280, height: 850 });
    const desktop = profileTrigger(page).locator(`[data-portrait-frame="${family}"]`);
    await expect(desktop).toBeVisible();
    await expect(desktop).toHaveCSS('width', '40px');
    shapes.get(40).add(await renderedFrame(desktop));
    if (captureDirectory) {
      portraits.push(captured);
    }
    await page.setViewportSize({ width: 375, height: 850 });
  }
  for (const [size, silhouettes] of shapes) expect(silhouettes.size, `Distinct frames at ${size}px`).toBe(frames.length);
  await page.evaluate(async () => (await import('/src/themes.js')).applyTheme('vigil'));
  const profile = page.getByRole('img', { name: 'Your profile picture with Far Horizons Frame', exact: true });
  await expect(profile).toBeVisible();
  await expect(profile.locator('.profile-portrait__initial')).toHaveText('A');
  await fitsViewport(page, profile);
  await fitsViewport(page, profileTrigger(page));
  if (captureDirectory) await page.screenshot({ path: join(captureDirectory, 'profile-dark-375.png') });
  expect(state.mutations).toEqual([]);
  if (captureDirectory) {
    // Copy the actual 40px navigation and 96px Profile compositions without
    // resizing a private PNG into a different, unreviewed geometry tier.
    await page.setViewportSize({ width: 1280, height: 850 });
    await page.evaluate((examples) => {
      const gallery = document.createElement('section');
      gallery.id = 'identity-visual-audit';
      Object.assign(gallery.style, { position: 'absolute', top: '0', left: '0', zIndex: '10000', width: '100%',
        background: 'var(--color-ink-page)', color: 'var(--color-ink-primary)', display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', padding: '24px' });
      examples.forEach(({ name, ...sizes }, index) => {
        const card = document.createElement('div');
        card.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:10px;border:1px solid var(--color-ink-page-shadow);border-radius:12px';
        const label = document.createElement('p');
        label.textContent = name;
        label.style.cssText = 'font:600 13px var(--font-body);text-align:center';
        const previews = document.createElement('div');
        previews.style.cssText = 'display:flex;align-items:center;gap:14px';
        for (const size of [40, 96]) {
          const html = sizes[size];
          const holder = document.createElement('div');
          holder.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:4px';
          const originalId = html.match(/<mask id="([^"]+)"/)?.[1];
          holder.innerHTML = originalId ? html.replaceAll(originalId, `audit-${index}-${size}`) : html;
          const sizeLabel = document.createElement('span');
          sizeLabel.textContent = `${size}px`;
          sizeLabel.style.cssText = 'font:600 11px var(--font-body)';
          holder.append(sizeLabel);
          previews.append(holder);
        }
        card.append(label, previews);
        gallery.append(card);
      });
      document.body.append(gallery);
    }, portraits);
    for (const theme of ['hyrule', 'vigil']) {
      await page.evaluate(async (name) => (await import('/src/themes.js')).applyTheme(name), theme);
      await page.locator('#identity-visual-audit').screenshot({ path: join(captureDirectory, `frames-${theme}.png`) });
    }
  }
});

async function renderedFrame(portrait) {
  const overlay = portrait.locator('[data-portrait-overlay]');
  if (await overlay.count()) {
    await expect(overlay).toBeVisible();
    await expect.poll(() => overlay.evaluate((image) => image.complete && image.naturalWidth > 0)).toBe(true);
    return overlay.getAttribute('src');
  }
  await expect(portrait.locator('svg')).toBeVisible();
  return portrait.locator('svg > g').evaluate((element) => element.innerHTML);
}
