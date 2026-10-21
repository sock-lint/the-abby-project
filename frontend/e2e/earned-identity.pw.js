import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
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
const title = { id: 201, slug: 'title-master-crafter', name: 'Master Crafter', item_type: 'cosmetic_title', icon: '🛠️', rarity: 'rare', metadata: { text: 'Master Crafter' } };
const badge = { id: 301, name: 'First Project', icon: '🏅', rarity: 'common', description: 'Finished your first project.' };
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

async function fixture(page, { parent = false, longNames = false, failedAvatar = false } = {}) {
  const user = {
    id: parent ? 902 : 901, username: parent ? 'synthetic-parent' : 'synthetic-maker', role: parent ? 'parent' : 'child',
    display_name: parent ? 'Sam Parent' : longNames ? 'Alexandria Verylongfamilyname The Enthusiastic Maker' : 'Alex Maker',
    avatar: failedAvatar ? `${origin}/synthetic-avatar-missing.png` : null, theme: 'hyrule',
    family: { id: 90, name: 'Synthetic Family', timezone: 'America/Phoenix' },
  };
  let identity = { id: user.id, username: user.username, display_name: user.display_name, avatar: user.avatar,
    active_frame: frames.find((frame) => frame.slug === 'frame-laurel'),
    active_title: longNames ? { ...title, metadata: { text: 'Extraordinarily Thoughtful Maker of Wonderful Things' } } : title,
    active_trophy_badge: badge };
  let maker = parent ? { ...identity, id: 901, username: 'synthetic-maker', display_name: 'Alex Maker', avatar: null,
    active_frame: frames.find((frame) => frame.slug === 'frame-steampunk'), active_title: title } : identity;
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
    const profile = { ...profileFixture, ...identity,
      avatar_configuration: { avatar_id: 'synthetic-unprepared', appearance: {}, accessories: {} } };
    const responses = {
      '/api/auth/me/': user,
      '/api/pulse/': { unread_count: 0, notifications: [], recent_drops: [], active_quest: null, companion_growth: { events: [] },
        expeditions_ready: [], savings_goals: [], newly_unlocked_lorebook: [], identity,
        header: { active_timer: null, coin_balance: 197, streak_days: 4 } },
      '/api/dashboard/': { active_timer: null, current_balance: '0.00', coin_balance: 197, this_week: {}, active_projects: [],
        recent_badges: [], savings_goals: [], next_actions: [], rpg: { ...profile, identity } },
      '/api/character/': profile,
      '/api/character/avatar/catalog/': { default_avatar_id: 'synthetic-unprepared', avatars: [] },
      '/api/cosmetics/': { active_frame: frames, active_title: [title] },
      '/api/cosmetics/catalog/': { active_frame: frames, active_title: [title] },
      '/api/badges/': [badge], '/api/achievements/summary/': { badges_earned: [badge] },
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

function profileTrigger(page) { return page.getByRole('button', { name: 'Open profile menu', exact: true }).filter({ visible: true }); }

async function fitsViewport(page, locator) {
  const width = page.viewportSize().width;
  const bounds = await locator.boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(-1);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
  const contentWidth = await locator.evaluate((element) => ({ scroll: element.scrollWidth, client: element.clientWidth }));
  expect(contentWidth.scroll, `Content overflows its ${contentWidth.client}px container`).toBeLessThanOrEqual(contentWidth.client + 1);
}

for (const width of [320, 375, 1280]) {
  test(`saved identity appears in navigation, Today and project signatures at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    const state = await fixture(page, { longNames: true, failedAvatar: true });
    await page.goto(origin);
    const today = page.getByRole('region', { name: 'Your look', exact: true });
    await expect(today).toContainText('Alexandria Verylongfamilyname');
    await expect(today).toContainText('Extraordinarily Thoughtful Maker of Wonderful Things');
    await expect(today).toContainText('First Project');
    await expect(today.locator('[data-portrait-frame="laurel"]')).toBeVisible();
    await expect(today.locator('.profile-portrait__initial')).toHaveText('A');
    await expect(today.locator('.profile-portrait__image img')).toHaveCount(0);
    const trigger = profileTrigger(page);
    await expect(trigger.locator('[data-portrait-frame="laurel"]')).toBeVisible();
    await expect(trigger).toContainText('Extraordinarily Thoughtful Maker of Wonderful Things');
    await expect(trigger.getByRole('img', { name: 'Featured badge: First Project', exact: true })).toBeVisible();
    if (captureDirectory) await page.screenshot({ path: join(captureDirectory, `today-${width}.png`) });
    await fitsViewport(page, today);
    await fitsViewport(page, trigger);
    const target = await trigger.boundingBox();
    expect(target.width).toBeGreaterThanOrEqual(44);
    expect(target.height).toBeGreaterThanOrEqual(44);
    await trigger.focus();
    await page.keyboard.press('ArrowDown');
    const menu = page.getByRole('menu', { name: 'Profile', exact: true });
    await expect(menu).toBeVisible();
    await expect(menu).toHaveCSS('transform', 'none');
    for (const item of await menu.getByRole('menuitem').all()) expect((await item.boundingBox()).height).toBeGreaterThanOrEqual(44);
    await expect(menu.getByRole('menuitem', { name: /Profile/ })).toBeFocused();
    await page.keyboard.press('End');
    await expect(menu.getByRole('menuitem', { name: /Settings/ })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(trigger).toBeFocused();
    await expect(menu).toHaveCount(0);
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

test('a parent sees the assigned maker identity rather than their own selection', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  const state = await fixture(page, { parent: true });
  await page.goto(`${origin}/quests/ventures/77`);
  await expect(profileTrigger(page)).toContainText('Sam Parent');
  await expect(profileTrigger(page).locator('[data-portrait-frame="laurel"]')).toBeVisible();
  const signature = page.getByRole('region', { name: 'Project maker', exact: true });
  await expect(signature).toContainText('Made by Alex Maker');
  await expect(signature.locator('[data-portrait-frame="steampunk"]')).toBeVisible();
  await expect(signature).not.toContainText('Sam Parent');
  expect(state.mutations).toEqual([]);
});

test('a confirmed Profile frame selection refreshes navigation and Today immediately', async ({ page }) => {
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
  expect(state.pulseReads()).toBeGreaterThan(before);
  expect(state.mutations).toEqual([{ path: '/api/character/equip/', method: 'POST', body: { item_id: 110 } }]);
  await trigger.click();
  await page.getByRole('menuitem', { name: /Profile/ }).press('Escape');
  await page.getByRole('link', { name: 'Today', exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole('region', { name: 'Your look', exact: true }).locator('[data-portrait-frame="steampunk"]')).toBeVisible();
  expect(state.mutations).toHaveLength(1);
});

test('all authored frame silhouettes render at navigation and Today sizes with a dark-theme fallback', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  const state = await fixture(page);
  await page.goto(origin);
  const today = page.getByRole('region', { name: 'Your look', exact: true });
  await expect(today).toBeVisible();
  const shapes = new Set();
  const portraits = [];
  for (const frame of frames) {
    const family = frame.slug.slice('frame-'.length);
    state.frame(family);
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const portrait = today.locator(`[data-portrait-frame="${family}"]`);
    await expect(portrait).toBeVisible();
    await expect(profileTrigger(page).locator(`[data-portrait-frame="${family}"]`)).toBeVisible();
    const overlay = portrait.locator('[data-portrait-overlay]');
    if (await overlay.count()) {
      await expect(overlay).toBeVisible();
      await expect.poll(() => overlay.evaluate((image) => image.complete && image.naturalWidth > 0)).toBe(true);
      shapes.add(await overlay.getAttribute('src'));
    } else {
      await expect(portrait.locator('svg')).toBeVisible();
      shapes.add(await portrait.locator('svg > g').evaluate((element) => element.innerHTML));
    }
    if (captureDirectory) portraits.push({ name: frame.name,
      smallHtml: await profileTrigger(page).locator(`[data-portrait-frame="${family}"]`).evaluate((element) => element.outerHTML),
      bigHtml: await portrait.evaluate((element) => element.outerHTML) });
  }
  expect(shapes.size).toBe(frames.length);
  await page.evaluate(async () => (await import('/src/themes.js')).applyTheme('vigil'));
  await expect(today.locator('[data-portrait-frame="far-horizons"]')).toBeVisible();
  await fitsViewport(page, today);
  if (captureDirectory) await page.screenshot({ path: join(captureDirectory, 'today-dark-375.png') });
  expect(state.mutations).toEqual([]);
  if (captureDirectory) {
    // Copy the actual 40px navigation and 64px Today compositions without
    // resizing a private PNG into a different, unreviewed geometry tier.
    await page.setViewportSize({ width: 1280, height: 850 });
    await page.evaluate((examples) => {
      const gallery = document.createElement('section');
      gallery.id = 'identity-visual-audit';
      Object.assign(gallery.style, { position: 'absolute', top: '0', left: '0', zIndex: '10000', width: '100%',
        background: 'var(--color-ink-page)', color: 'var(--color-ink-primary)', display: 'grid',
        gridTemplateColumns: 'repeat(6, 1fr)', gap: '12px', padding: '24px' });
      examples.forEach(({ name, smallHtml, bigHtml }, index) => {
        const card = document.createElement('div');
        card.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:10px;border:1px solid var(--color-ink-page-shadow);border-radius:12px';
        const label = document.createElement('p');
        label.textContent = name;
        label.style.cssText = 'font:600 13px var(--font-body);text-align:center';
        const previews = document.createElement('div');
        previews.style.cssText = 'display:flex;align-items:center;gap:14px';
        for (const [size, html] of [[40, smallHtml], [64, bigHtml]]) {
          const holder = document.createElement('div');
          const originalId = html.match(/<mask id="([^"]+)"/)?.[1];
          holder.innerHTML = originalId ? html.replaceAll(originalId, `audit-${index}-${size}`) : html;
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
