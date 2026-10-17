import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

const root = fileURLToPath(new URL('..', import.meta.url));
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find(entry => entry.family_id === 'meshtint-pedestal-card-ui');
const privatePayloadPresent = !!pin && existsSync(new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url));
const screenshotDirectory = process.env.ABBY_PRIVATE_ACCEPTANCE_DIR;
if (screenshotDirectory && (!isAbsolute(screenshotDirectory) || !relative(resolve(root, '..'), resolve(screenshotDirectory)).startsWith('..'))) {
  throw new Error('ABBY_PRIVATE_ACCEPTANCE_DIR must be an absolute private directory outside the checkout.');
}
let server, origin;

// Purchased artwork must never appear in public CI attachments. A developer
// can explicitly opt into screenshots in a private directory outside Git.
test.use({ trace: 'off', video: 'off', screenshot: 'off' });
test.beforeAll(async () => {
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: root,
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolveOrigin, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Storybook acceptance server startup timed out.')), 30_000);
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Acceptance server exited ${code}.`)); });
    server.stdout.on('data', chunk => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolveOrigin(match[0]); }
    });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

async function open(page, { theme = 'hyrule', large = false, long = true, failImages = false, starState = 'missing', view = 'components' } = {}) {
  const errors = [];
  const apiRequests = [];
  const pendingStars = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (url.pathname === '/api/auth/me/' && route.request().method() === 'GET') return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 7001, username: 'synthetic-storybook-child', role: 'child' }) });
    if (url.pathname.startsWith('/api/')) { apiRequests.push(url.pathname); return route.abort(); }
    if (url.pathname.startsWith('/synthetic/storybook-star-')) {
      if (starState === 'loading') { pendingStars.push(route); return; }
      return route.abort();
    }
    if (failImages && route.request().resourceType() === 'image' && url.pathname.endsWith('.png')) return route.abort();
    return route.continue();
  });
  await page.goto(`${origin}/e2e/storybook-accents-fixture.html?theme=${theme}&long=${long ? 1 : 0}&large=${large ? 1 : 0}&star-state=${starState}&view=${view}`, { waitUntil: starState === 'loading' ? 'domcontentloaded' : 'load' });
  await page.evaluate(() => document.fonts.ready);
  if (view === 'composition') await expect(page.locator('[data-composed-ready]')).toHaveCount(1);
  else await expect(page.locator('[data-bonus-star]')).toHaveCount(2);
  return { errors, apiRequests, releasePendingStars: () => Promise.all(pendingStars.map(route => route.abort())) };
}

// Use each rendered text line rather than its parent's box: the parent can
// legitimately span empty space beside artwork, while text must stay clear.
async function layoutProblems(page) {
  return page.evaluate(() => {
    const problems = [];
    const rect = element => element.getBoundingClientRect();
    const overlaps = (a, b, gap = 0) => a.left < b.right + gap - 0.5 && a.right > b.left - gap + 0.5 && a.top < b.bottom + gap - 0.5 && a.bottom > b.top - gap + 0.5;
    const visible = element => getComputedStyle(element).display !== 'none' && rect(element).width > 0 && rect(element).height > 0;
    const textRects = container => {
      const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      const result = [];
      let node;
      while ((node = walker.nextNode())) {
        if (!node.textContent.trim() || node.parentElement.closest('[aria-hidden="true"], [data-pedestal-image]')) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const bounds of range.getClientRects()) if (bounds.width && bounds.height) result.push({ bounds, text: node.textContent.trim().slice(0, 45) });
      }
      return result;
    };
    for (const card of document.querySelectorAll('[data-storybook-panel]')) {
      const art = [...card.querySelectorAll('[data-storybook-corner]')].map(rect);
      for (const { bounds, text } of textRects(card)) for (const corner of art) {
        if (overlaps(bounds, corner, 8)) problems.push(`Panel text within eight pixels of corner: ${text}`);
      }
      for (const button of card.querySelectorAll('button')) for (const corner of art) {
        if (overlaps(rect(button), corner, 8)) problems.push(`Panel control within eight pixels of corner: ${button.textContent.trim()}`);
      }
      for (const corner of art) {
        const cardBounds = rect(card);
        if (corner.left < cardBounds.left || corner.right > cardBounds.right || corner.top < cardBounds.top || corner.bottom > cardBounds.bottom) problems.push('Corner extends outside its card');
      }
    }
    for (const feature of document.querySelectorAll('.storybook-feature')) {
      const art = feature.querySelector('.storybook-feature__art');
      const content = feature.querySelector('.storybook-feature__content');
      if (art && visible(art) && overlaps(rect(art), rect(content), 12)) problems.push('Card artwork lacks twelve pixels of content clearance');
      for (const { bounds, text } of textRects(content)) {
        if (bounds.left < rect(content).left - 1 || bounds.right > rect(content).right + 1) problems.push(`Feature text overflows its content column: ${text}`);
      }
    }
    for (const trophy of document.querySelectorAll('[data-trophy-slot]')) {
      const art = trophy.querySelector('[data-pedestal-image="frame-gold"]');
      for (const { bounds, text } of textRects(trophy)) {
        if (art && overlaps(bounds, rect(art), 4)) problems.push(`Profile text encroaches on its frame: ${text}`);
        if (bounds.left < rect(trophy).left - 1 || bounds.right > rect(trophy).right + 1) problems.push(`Profile text overflows its slot: ${text}`);
      }
    }
    for (const button of document.querySelectorAll('main button')) {
      const bounds = rect(button);
      if (bounds.left < -1 || bounds.right > innerWidth + 1) problems.push(`Control overflows viewport: ${button.textContent.trim().slice(0, 45)}`);
    }
    if (document.documentElement.scrollWidth > innerWidth) problems.push('Page overflows horizontally');
    return problems;
  });
}

async function privateCapture(page, name, locator) {
  if (!screenshotDirectory) return;
  mkdirSync(screenshotDirectory, { recursive: true, mode: 0o700 });
  const options = { path: resolve(screenshotDirectory, `${name}.png`) };
  if (locator) await locator.screenshot(options);
  else await page.screenshot({ ...options, fullPage: true });
}

async function fallbackStarMeasurements(stars) {
  return stars.evaluateAll(elements => elements.map(element => {
    const box = element.getBoundingClientRect();
    const placeholder = element.matches('.mt-image-placeholder') ? element : element.querySelector('.mt-image-placeholder');
    const style = getComputedStyle(placeholder);
    const walker = document.createTreeWalker(placeholder, NodeFilter.SHOW_TEXT);
    const glyphs = [];
    let node;
    while ((node = walker.nextNode())) {
      if (!node.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const bounds of range.getClientRects()) glyphs.push({ x: bounds.x - box.x, y: bounds.y - box.y, width: bounds.width, height: bounds.height });
    }
    return {
      asset: element.dataset.pedestalImage, state: element.dataset.imageState,
      width: box.width, height: box.height,
      padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft],
      fontSize: style.fontSize, glyphs,
      silent: placeholder.getAttribute('aria-hidden') === 'true' || !!placeholder.closest('[aria-hidden="true"]'),
    };
  }));
}

function fallbackStarProblems(records) {
  return records.flatMap(record => {
    const problems = [];
    if (record.width !== 20 || record.height !== 20) problems.push('Fallback changed the 20px star canvas.');
    if (record.padding.some(value => value !== '0px')) problems.push('Fallback retained placeholder padding.');
    if (!record.silent) problems.push('Decorative fallback was exposed to assistive technology.');
    if (!record.glyphs.length || record.glyphs.some(glyph => glyph.x < -0.5 || glyph.y < -0.5 || glyph.x + glyph.width > record.width + 0.5 || glyph.y + glyph.height > record.height + 0.5)) problems.push('Fallback glyph extends outside its star canvas.');
    return problems.length ? [{ ...record, problems }] : [];
  });
}

async function badgeGlyphProblems(page) {
  return page.locator('[data-badge-artwork]').evaluateAll(elements => elements.flatMap(element => {
    const well = element.querySelector('.mt-frame__opening') || element;
    const glyph = well.querySelector(':scope > span');
    if (!glyph || !glyph.firstChild) return [{ problem: 'Missing badge glyph' }];
    const range = document.createRange();
    range.selectNodeContents(glyph);
    const canvas = well.getBoundingClientRect();
    const bounds = range.getBoundingClientRect();
    if (bounds.left >= canvas.left - 0.5 && bounds.right <= canvas.right + 0.5 && bounds.top >= canvas.top - 0.5 && bounds.bottom <= canvas.bottom + 0.5) return [];
    return [{ variant: element.dataset.badgeArtwork, icon: glyph.textContent, canvas: { width: canvas.width, height: canvas.height }, glyph: { x: bounds.x - canvas.x, y: bounds.y - canvas.y, width: bounds.width, height: bounds.height }, problem: 'Badge glyph extends beyond its own artwork well' }];
  }));
}

test('shared decorated panels preserve corners, content clearance and direct-child spacing', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const [width, large] of [[320, false], [375, true], [1280, false]]) {
    await page.setViewportSize({ width, height: 900 });
    const result = await open(page, { view: 'composition', large, theme: width === 375 ? 'vigil' : 'hyrule' });
    await expect(page.getByRole('region', { name: 'Parent Today', exact: true }).locator('[data-storybook-corner]')).toHaveCount(2);
    await expect(page.locator('[data-decor-kind="seal"] [data-storybook-corner]')).toHaveCount(1);
    await expect(page.locator('[data-decor-kind="combined"] [data-storybook-corner]')).toHaveCount(2);
    const spacing = await page.locator('[data-rhythm-panel]').evaluate(element => {
      const children = [...element.querySelectorAll(':scope > [data-rhythm-child]')].map(child => child.getBoundingClientRect());
      const box = element.getBoundingClientRect();
      return {
        gaps: children.slice(1).map((child, index) => child.top - children[index].bottom),
        corners: [...element.querySelectorAll('[data-storybook-corner]')].map(corner => {
          const bounds = corner.getBoundingClientRect();
          return { width: bounds.width, height: bounds.height, insetX: Math.min(bounds.left - box.left, box.right - bounds.right), insetY: Math.min(bounds.top - box.top, box.bottom - bounds.bottom) };
        }),
        paddingTop: getComputedStyle(element).paddingTop, paddingBottom: getComputedStyle(element).paddingBottom,
      };
    });
    expect(spacing.gaps).toEqual([16, 16]);
    expect(spacing.paddingTop).toBe('40px');
    expect(spacing.paddingBottom).toBe('40px');
    for (const corner of spacing.corners) {
      expect(corner.width).toBe(20);
      expect(corner.height).toBe(20);
      expect(corner.insetX).toBeCloseTo(9, 0);
      expect(corner.insetY).toBeCloseTo(9, 0);
    }
    expect(await layoutProblems(page)).toEqual([]);
    expect(result.errors).toEqual([]);
    expect(result.apiRequests).toEqual([]);
    await privateCapture(page, `storybook-consistency-${width}-${large ? 'large' : 'normal'}`);
    await page.unroute('**/*');
  }
});

test('shared badge glyphs stay inside their artwork at enlarged text sizes', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const problems = [];
  for (const [width, large] of [[375, false], [320, true], [375, true]]) {
    await page.setViewportSize({ width, height: 900 });
    await open(page, { view: 'composition', large });
    problems.push(...(await badgeGlyphProblems(page)).map(problem => ({ ...problem, width, large })));
    await page.unroute('**/*');
  }
  expect(problems).toEqual([]);
});

test('badge collection, earned detail and trophy picker share artwork while preserving selection', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 900 });
  const result = await open(page, { view: 'composition', large: true, failImages: true });
  const collection = page.getByRole('region', { name: 'Badge collection', exact: true });
  await expect(collection.locator('[data-badge-artwork="tile"]')).toHaveCount(3);
  await expect(collection.locator('[data-pedestal-image="frame-gold"]')).toHaveCount(0);
  await collection.getByRole('button').first().click();
  let dialog = page.getByRole('dialog');
  await expect(dialog.locator('[data-badge-artwork="featured"]')).toHaveCount(1);
  const frame = dialog.locator('[data-pedestal-image="frame-gold"]');
  await dialog.locator('[data-badge-artwork="featured"]').scrollIntoViewIfNeeded();
  await expect(frame).toHaveAttribute('data-image-state', privatePayloadPresent ? 'error' : 'unavailable');
  expect(await badgeGlyphProblems(page)).toEqual([]);
  await privateCapture(page, 'storybook-earned-badge-detail-fallback');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await collection.getByRole('button').last().click();
  dialog = page.getByRole('dialog');
  await expect(dialog.locator('[data-pedestal-image="frame-gold"]')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  const profile = page.getByRole('region', { name: 'Composed profile', exact: true });
  await profile.locator('[data-trophy-slot]').click();
  dialog = page.getByRole('dialog', { name: 'Choose your trophy badge', exact: true });
  const current = dialog.getByRole('button', { pressed: true });
  await expect(current).toHaveCount(1);
  await expect(dialog.locator('li button')).toHaveCount(2);
  await expect(dialog.locator('li button[aria-pressed="false"]')).toHaveCount(1);
  const marker = current.locator('[data-trophy-current-marker]');
  await expect(marker).toBeVisible();
  const badgeButtons = dialog.locator('li button');
  const bounds = await badgeButtons.evaluateAll(buttons => buttons.map(button => {
    const box = button.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, right: box.right };
  }));
  expect(bounds[0].y).toBeCloseTo(bounds[1].y, 0);
  expect(bounds[0].right).toBeLessThan(bounds[1].x);
  expect(bounds.every(box => box.x >= 0 && box.right <= 320)).toBe(true);
  expect(await badgeGlyphProblems(page)).toEqual([]);
  await privateCapture(page, 'storybook-trophy-picker-large');
  await current.focus();
  await current.press('Space');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('[data-fixture-event]')).toHaveText('Clear synthetic trophy');
  await profile.locator('[data-trophy-slot]').click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { pressed: true })).toHaveCount(0);
  const other = dialog.getByRole('button', { name: /^ExtraordinarilyHelpful/ });
  await other.focus();
  await other.press('Enter');
  await expect(page.locator('[data-fixture-event]')).toHaveText('Choose synthetic trophy 82');
  await profile.locator('[data-trophy-slot]').click();
  await expect(page.getByRole('dialog').getByRole('button', { name: /^ExtraordinarilyHelpful/, pressed: true })).toHaveCount(1);
  expect(result.errors).toEqual([]);
  expect(result.apiRequests).toEqual([]);
});

test('composed Challenges keeps readable content beside its artwork at desktop grid boundaries', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const records = [];
  for (const width of [320, 375, 1279, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await open(page, { view: 'composition', long: true, large: width <= 375 });
    const cards = page.getByRole('region', { name: 'Parent goals', exact: true }).locator('article');
    await expect(cards).toHaveCount(2);
    for (const card of await cards.all()) {
      const image = card.locator('[data-pedestal-image]');
      await card.evaluate(element => element.scrollIntoView({ block: 'start' }));
      if (privatePayloadPresent) await expect(image).toHaveAttribute('data-image-state', 'ready');
      records.push(await card.evaluate((element, viewport) => {
        const art = element.querySelector('[data-storybook-card-art]').getBoundingClientRect();
        const content = element.querySelector('[data-storybook-card-content]').getBoundingClientRect();
        return { viewport, cardWidth: element.getBoundingClientRect().width, artWidth: art.width, contentWidth: content.width, sideBySide: art.right <= content.left + 1 && art.top < content.bottom && art.bottom > content.top };
      }, width));
    }
    await privateCapture(page, `storybook-composed-challenges-${width}`);
    await page.unroute('**/*');
  }
  expect(records.filter(record => record.sideBySide && record.contentWidth < 256), JSON.stringify(records)).toEqual([]);
});

for (const starState of ['missing', 'loading', 'error']) {
  test(`${starState} private star fallbacks stay silent and inside their canvas with normal and enlarged text`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    const records = [];
    for (const large of [false, true]) {
      const result = await open(page, { large, starState });
      const stars = page.locator('[data-star-fallbacks] [data-pedestal-image]');
      await expect(stars).toHaveCount(2);
      for (const star of await stars.all()) {
        await expect(star).toHaveAttribute('data-image-state', starState === 'missing' ? 'unavailable' : starState);
      }
      records.push(...(await fallbackStarMeasurements(stars)).map(record => ({ ...record, textScale: large ? '200%' : 'normal' })));
      expect(result.errors).toEqual([]);
      expect(result.apiRequests).toEqual([]);
      await result.releasePendingStars();
      await page.unroute('**/*');
    }
    expect(fallbackStarProblems(records), JSON.stringify(records)).toEqual([]);
  });
}

for (const failImages of [false, true]) {
  test(`${failImages ? 'failed' : 'available'} artwork keeps Today, Profile, challenge and reward text clear at phone and desktop widths`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const theme of ['hyrule', 'vigil']) {
      for (const width of [320, 375, 1280]) {
        for (const large of [false, true]) {
          await page.setViewportSize({ width, height: 812 });
          const result = await open(page, { theme, large, failImages });
          const heroes = page.locator('[data-hero-variant]');
          await expect(heroes).toHaveCount(4);
          await expect(heroes.locator('[data-storybook-corner]')).toHaveCount(8);
          await expect(heroes.locator('[data-storybook-panel]')).toHaveCount(4);
          await expect.poll(() => layoutProblems(page), { message: `${theme}, ${width}px, ${large ? '200%' : 'normal'} text, ${failImages ? 'failed' : 'available'} artwork` }).toEqual([]);
          expect(result.errors).toEqual([]);
          expect(result.apiRequests).toEqual([]);
          if (!failImages && !large && width === 375) await privateCapture(page, `storybook-${theme}-phone`);
          await page.unroute('**/*');
        }
      }
    }
  });
}

test('private release PNGs render completely and failed art collapses without hiding actions', async ({ page }) => {
  test.skip(!privatePayloadPresent, 'Private immutable payload absent; actual PNG rendering acceptance remains pending.');
  await page.setViewportSize({ width: 375, height: 812 });
  const result = await open(page);
  const syntheticFallbacks = page.locator('[data-star-fallbacks] [data-pedestal-image]');
  await expect(syntheticFallbacks).toHaveCount(2);
  for (const fallback of await syntheticFallbacks.all()) await expect(fallback).toHaveAttribute('data-image-state', 'unavailable');
  const images = page.locator('main > section [data-pedestal-image]');
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded();
    await expect(image).toHaveAttribute('data-image-state', 'ready');
    const png = image.locator('img');
    expect(await png.evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
    expect(await png.evaluate(element => getComputedStyle(element).objectFit)).toBe('contain');
    expect(await png.evaluate(element => Math.abs(element.getBoundingClientRect().width - element.getBoundingClientRect().height) < 1)).toBe(true);
  }
  await expect(page.locator('.storybook-feature__art')).toHaveCount(3);
  expect(result.errors).toEqual([]);
  await privateCapture(page, 'storybook-private-rendered');
  await page.unroute('**/*');
  await open(page, { failImages: true });
  for (const image of await page.locator('.storybook-feature__art [data-pedestal-image]').all()) {
    // Once the failed lazy PNG arrives its art column disappears. Scroll the
    // surviving feature, since Playwright cannot act on its now-hidden image.
    await image.evaluate(element => element.closest('.storybook-feature').scrollIntoView());
    await expect(image).toHaveAttribute('data-image-state', 'error');
  }
  await expect(page.locator('.storybook-feature__art:visible')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Open projects' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Request reward', exact: true })).toBeEnabled();
  expect(await layoutProblems(page)).toEqual([]);
  await page.unroute('**/*');
  await open(page, { long: false });
  for (const [name, locator] of [
    ['today', page.locator('[data-hero-variant="next-action"]')],
    ['profile', page.getByRole('region', { name: 'Profile trophy', exact: true })],
    ['challenges', page.getByRole('region', { name: 'Challenge card', exact: true })],
    ['rewards', page.getByRole('region', { name: 'Reward shop', exact: true })],
    ['daily-bonus', page.getByRole('region', { name: 'Daily bonus', exact: true })],
  ]) {
    await locator.scrollIntoViewIfNeeded();
    for (const image of await locator.locator('[data-pedestal-image]').all()) await expect(image).toHaveAttribute('data-image-state', 'ready');
    await privateCapture(page, `storybook-${name}-phone`, locator);
  }
});

test('decorations preserve trophy keyboard access, challenge actions and reward availability', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 });
  const result = await open(page, { large: true, failImages: true });
  const compactTrophy = page.locator('[data-trophy-example="compact"] button');
  await compactTrophy.focus();
  await compactTrophy.press('Enter');
  await expect(page.locator('[data-fixture-event]')).toHaveText('Open compact trophy picker');
  await expect(page.locator('[data-trophy-example="empty"] [data-pedestal-image]')).toHaveCount(0);
  await expect(page.locator('[data-bonus-star="pending"] [data-pedestal-image="star-unlit"]')).toHaveCount(1);
  await expect(page.locator('[data-bonus-star="awarded"] [data-pedestal-image="star-lit"]')).toHaveCount(1);
  await expect(page.getByRole('img', { name: 'Difficulty: 3 out of 5' })).toBeVisible();
  await page.locator('[data-hero-variant="next-action"]').getByRole('button', { name: /^Complete / }).click();
  await expect(page.locator('[data-fixture-event]')).toHaveText('Complete chore 71');
  const challenge = page.getByRole('region', { name: 'Challenge card', exact: true });
  await challenge.getByRole('button', { name: 'Unpin', exact: true }).click();
  await expect(challenge.getByRole('button', { name: 'Pin to Today', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await challenge.getByRole('button', { name: /^View / }).click();
  await expect(page.locator('[data-fixture-event]')).toHaveText('View synthetic challenge');
  const shop = page.getByRole('region', { name: 'Reward shop', exact: true });
  await expect(shop.getByRole('button', { name: 'Out of stock', exact: true })).toBeDisabled();
  await shop.getByRole('button', { name: 'Request reward', exact: true }).click();
  await expect(page.locator('[data-fixture-event]')).toHaveText('Request reward 21');
  await page.getByRole('button', { name: 'Open projects', exact: true }).click();
  await expect(page.locator('[data-fixture-location]')).toHaveText('/quests?tab=ventures');
  expect(result.errors).toEqual([]);
  expect(result.apiRequests).toEqual([]);
});
