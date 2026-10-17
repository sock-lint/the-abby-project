import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find(entry => entry.family_id === 'meshtint-pedestal-card-ui');
const privateArt = !!pin && existsSync(new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url));
const screenshots = process.env.ABBY_PRIVATE_ACCEPTANCE_DIR;
if (screenshots && (!isAbsolute(screenshots) || !relative(resolve(frontend, '..'), resolve(screenshots)).startsWith('..'))) {
  throw new Error('ABBY_PRIVATE_ACCEPTANCE_DIR must be an absolute private path outside the checkout.');
}
let server, origin;
test.use({ trace: 'off', video: 'off', screenshot: 'off' });
test.beforeAll(async () => {
  server = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: frontend,
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolveOrigin, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Profile card fixture startup timed out.')), 30_000);
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Profile card fixture exited ${code}.`)); });
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

async function open(page, { theme = 'hyrule', large = false, long = false, owned = 'all', frame = 'nature', failImages = false } = {}) {
  const errors = [], unexpected = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) { unexpected.push('Outside-origin request'); return route.abort(); }
    if (url.pathname === '/api/auth/me/' && request.method() === 'GET') return route.fulfill({ json: { id: 1, username: 'card-style-fixture-child', role: 'child', theme } });
    if (url.pathname.startsWith('/api/')) { unexpected.push(`${request.method()} ${url.pathname}`); return route.abort(); }
    if (failImages && request.resourceType() === 'image' && url.pathname.endsWith('.png')) return route.abort();
    return route.continue();
  });
  await page.goto(`${origin}/e2e/profile-card-styles-fixture.html?theme=${theme}&large=${large ? 1 : 0}&long=${long ? 1 : 0}&owned=${owned}&frame=${frame}`);
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('[data-trophy-slot]')).toHaveCount(1);
  return { errors, unexpected };
}

async function capture(locator, name) {
  if (!screenshots) return;
  mkdirSync(screenshots, { recursive: true, mode: 0o700 });
  await locator.screenshot({ path: resolve(screenshots, `${name}.png`) });
}

async function settleArt(page, { failed = false } = {}) {
  for (const image of await page.locator('[data-profile-card-art] [data-pedestal-image]').all()) {
    await image.evaluate(element => element.closest('[data-trophy-slot], [data-cosmetic-sigil]').scrollIntoView({ block: 'center' }));
    await expect(image).toHaveAttribute('data-image-state', privateArt ? failed ? 'error' : 'ready' : 'unavailable');
  }
}

async function layoutProblems(page) {
  return page.evaluate(() => {
    const problems = [];
    const rect = element => element.getBoundingClientRect();
    const inside = (a, b) => a.left >= b.left - 1 && a.right <= b.right + 1 && a.top >= b.top - 1 && a.bottom <= b.bottom + 1;
    const overlap = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    if (document.documentElement.scrollWidth > innerWidth) problems.push('Page overflows horizontally');
    for (const surface of document.querySelectorAll('[data-trophy-slot], [data-cosmetic-sigil]')) {
      const bounds = rect(surface);
      const walker = document.createTreeWalker(surface, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if (!node.textContent.trim() || node.parentElement.closest('[aria-hidden="true"], [data-profile-card-art], [data-badge-artwork]')) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        for (const line of range.getClientRects()) {
          if (line.width && line.height && !inside(line, bounds)) problems.push(`Text clips outside its surface: ${node.textContent.trim().slice(0, 55)}`);
        }
      }
      for (const art of surface.querySelectorAll('[data-profile-card-art]')) {
        if (!rect(art).width || !rect(art).height) continue;
        if (!inside(rect(art), bounds)) problems.push('Whole card canvas extends beyond its owner');
        const copy = surface.querySelector('[data-trophy-copy]');
        if (copy && overlap(rect(art), rect(copy))) problems.push('Badge identity overlaps the original card canvas');
        if (art.querySelector('[data-badge-artwork], [data-badge-rarity]')) problems.push('Badge identity is nested inside decorative artwork');
      }
    }
    for (const button of document.querySelectorAll('button')) if (rect(button).left < -1 || rect(button).right > innerWidth + 1) problems.push('Control exceeds the viewport');
    return problems;
  });
}

function expectClean(result) {
  expect(result.errors).toEqual([]);
  expect(result.unexpected).toEqual([]);
}

async function statsProblems(page) {
  return page.getByRole('region', { name: 'Profile frontispiece', exact: true }).locator('dl').evaluate(element => {
    const columns = [...element.children].map(column => {
      const lines = [], walker = document.createTreeWalker(column, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if (!node.textContent.trim()) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        for (const bounds of range.getClientRects()) if (bounds.width && bounds.height) lines.push({ text: node.textContent.trim(), left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom });
      }
      return lines;
    });
    const problems = [];
    for (let index = 0; index < columns.length; index++) for (const line of columns[index]) {
      for (const neighbor of columns.slice(index + 1).flat()) {
        if (line.left < neighbor.right - 0.5 && line.right > neighbor.left + 0.5 && line.top < neighbor.bottom - 0.5 && line.bottom > neighbor.top + 0.5) problems.push({ problem: 'Neighboring Profile stat text overlaps', line, neighbor });
      }
    }
    return problems;
  });
}

test('Profile card art stays separate from real badge identity at narrow and desktop text sizes', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const [width, large, theme] of [[320, false, 'hyrule'], [320, true, 'vigil'], [1280, false, 'hyrule'], [1280, true, 'vigil']]) {
    await page.setViewportSize({ width, height: 900 });
    const result = await open(page, { theme, large, long: large, owned: large ? 'partial' : 'all' });
    await settleArt(page);
    const trophy = page.locator('[data-trophy-slot]');
    await expect(trophy).toHaveAttribute('data-frame-card-style', 'card-front-nature');
    await expect(trophy.locator('[data-badge-artwork="tile"]')).toHaveCount(1);
    await expect(trophy.locator('[data-badge-rarity]')).toHaveText('legendary');
    await expect(trophy.locator('[data-profile-card-label]')).toHaveText('Nature card style');
    if (width === 320) {
      const identity = await trophy.locator('.profile-trophy__identity').evaluate(element => {
        const bounds = node => { const { left, right, top, bottom, width } = node.getBoundingClientRect(); return { left, right, top, bottom, width }; };
        return { area: bounds(element), badge: bounds(element.querySelector('[data-badge-artwork]')), copy: bounds(element.querySelector('.profile-trophy__identity-copy')) };
      });
      if (large) {
        expect(identity.copy.top).toBeGreaterThanOrEqual(identity.badge.bottom);
        expect(identity.copy.width).toBeCloseTo(identity.area.width, 0);
      } else {
        expect(identity.copy.left).toBeGreaterThanOrEqual(identity.badge.right);
        expect(Math.min(identity.copy.bottom, identity.badge.bottom) - Math.max(identity.copy.top, identity.badge.top)).toBeGreaterThan(0);
      }
    }
    if (width === 320 && large) await capture(page.getByRole('region', { name: 'Profile frontispiece', exact: true }), 'profile-card-320-vigil-large');
    expect(await statsProblems(page)).toEqual([]);
    expect(await layoutProblems(page)).toEqual([]);
    expectClean(result);
    if (!large) {
      await capture(page.getByRole('region', { name: 'Profile frontispiece', exact: true }), `profile-card-${width}-${theme}`);
      await capture(page.locator('.profile-card-collection').locator('..'), `card-collection-${width}-${theme}`);
    }
    await page.unroute('**/*');
  }
});

test('locked frames stay noninteractive while owned card styles equip and remove by keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  let result = await open(page, { owned: 'partial' });
  const locked = page.getByRole('img', { name: 'Scholar Frame · rare · not yet owned', exact: true });
  await expect(locked).toHaveCount(1);
  await expect(locked.locator('button, [tabindex]')).toHaveCount(0);
  expect(await locked.evaluate(element => element.tabIndex)).toBe(-1);
  await locked.click();
  await expect(page.locator('[data-fixture-event]')).toHaveText('No action taken');
  await expect(page.locator('[data-trophy-slot]')).toHaveAttribute('data-frame-card-style', 'card-front-nature');
  const ranger = page.getByRole('button', { name: /^Ranger's Cap Frame · rare ·/ });
  await expect(ranger).toHaveAttribute('aria-pressed', 'true');
  await ranger.focus(); await ranger.press('Enter');
  await expect(page.locator('[data-fixture-event]')).toHaveText('Remove synthetic frame active_frame');
  await expect(page.locator('[data-trophy-slot]')).not.toHaveAttribute('data-frame-card-style');
  await ranger.focus(); await ranger.press('Space');
  await expect(page.locator('[data-fixture-event]')).toHaveText('Equip synthetic frame 401');
  expectClean(result);
  await page.unroute('**/*');
  result = await open(page);
  const scholar = page.getByRole('button', { name: /Scholar Frame.*click to equip/ });
  await scholar.focus(); await scholar.press('Space');
  await expect(page.locator('[data-fixture-event]')).toHaveText('Equip synthetic frame 402');
  await expect(page.locator('[data-trophy-slot]')).toHaveAttribute('data-frame-card-style', 'card-front-light');
  await expect(page.locator('[data-profile-card-label]')).toHaveText('Light card style');
  await expect(page.locator('[data-trophy-slot]')).toHaveAccessibleName('Trophy badge: Thoughtful creator. Click to change or clear.');
  await expect(page.locator('[data-trophy-slot] [data-badge-rarity]')).toHaveText('legendary');
  expectClean(result);
});

test('trophy picker changes only the earned badge and preserves its independently equipped card style', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const result = await open(page, { large: true, long: true });
  const trophy = page.locator('[data-trophy-slot]');
  await trophy.focus(); await trophy.press('Enter');
  let dialog = page.getByRole('dialog', { name: 'Choose your trophy badge', exact: true });
  await expect(dialog.locator('li button')).toHaveCount(2);
  const current = dialog.getByRole('button', { pressed: true });
  await current.focus(); await current.press('Space');
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('[data-fixture-event]')).toHaveText('Clear synthetic trophy');
  await expect(trophy).toHaveAttribute('data-filled', 'false');
  await expect(trophy).toHaveAttribute('data-frame-card-style', 'card-front-nature');
  await trophy.click();
  dialog = page.getByRole('dialog');
  const other = dialog.getByRole('button', { name: /^ExtraordinarilyHelpful/ });
  await other.focus(); await other.press('Enter');
  await expect(page.locator('[data-fixture-event]')).toHaveText('Choose synthetic trophy 82');
  await expect(trophy).toHaveAttribute('data-frame-card-style', 'card-front-nature');
  await expect(trophy.locator('[data-badge-rarity]')).toHaveText('rare');
  expect(await layoutProblems(page)).toEqual([]);
  expectClean(result);
});

test('missing and failed card art collapses without losing identity, style labels or collection controls', async ({ page }) => {
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const result = await open(page, { failImages: true, large: width === 320, long: width === 320 });
    await settleArt(page, { failed: true });
    await expect(page.locator('[data-profile-card-art]:visible')).toHaveCount(0);
    await expect(page.locator('.profile-card-style-fallback:visible')).toHaveCount(2);
    const trophy = page.locator('[data-trophy-slot]');
    await expect(trophy.locator('[data-profile-card-label]')).toHaveText('Nature card style');
    const emptyGutter = await trophy.evaluate(element => element.getBoundingClientRect().height - element.querySelector('[data-trophy-copy]').getBoundingClientRect().height);
    expect(emptyGutter).toBeLessThanOrEqual(40);
    expect(await layoutProblems(page)).toEqual([]);
    expectClean(result);
    await page.unroute('**/*');
  }
  const result = await open(page, { frame: 'legacy' });
  await expect(page.locator('[data-trophy-slot] [data-profile-card-art]')).toHaveCount(0);
  await expect(page.locator('[data-trophy-slot] [data-badge-artwork="tile"]')).toHaveCount(1);
  expectClean(result);
});

test('private Nature and Light PNGs retain their complete transparent square canvas', async ({ page }) => {
  test.skip(!privateArt, 'Private immutable pedestal payload absent; original PNG acceptance remains pending.');
  await page.setViewportSize({ width: 320, height: 900 });
  const result = await open(page);
  for (const [asset, name] of [['card-front-nature', null], ['card-front-light', 'Scholar Frame']]) {
    if (name) await page.getByRole('button', { name: new RegExp(`${name}.*click to equip`) }).click();
    await settleArt(page);
    const image = page.locator(`[data-trophy-slot] [data-pedestal-image="${asset}"] img`);
    const canvas = await image.evaluate(img => {
      const canvas = document.createElement('canvas'); canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
      const context = canvas.getContext('2d'); context.drawImage(img, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let transparent = 0, opaque = 0;
      for (let index = 3; index < pixels.length; index += 4) { if (pixels[index] === 0) transparent++; if (pixels[index] === 255) opaque++; }
      const style = getComputedStyle(img), bounds = img.getBoundingClientRect();
      return { naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight, objectFit: style.objectFit, clipPath: style.clipPath, maskImage: style.maskImage, width: bounds.width, height: bounds.height, transparent, opaque, corners: [pixels[3], pixels[(canvas.width - 1) * 4 + 3], pixels[((canvas.height - 1) * canvas.width) * 4 + 3], pixels[pixels.length - 1]] };
    });
    expect(canvas.naturalWidth).toBe(512); expect(canvas.naturalHeight).toBe(512);
    expect(canvas.objectFit).toBe('contain'); expect(canvas.clipPath).toBe('none'); expect(canvas.maskImage).toBe('none');
    expect(canvas.width).toBeCloseTo(canvas.height, 0);
    expect(canvas.transparent).toBeGreaterThan(100); expect(canvas.opaque).toBeGreaterThan(100); expect(canvas.corners).toEqual([0, 0, 0, 0]);
    expect(await layoutProblems(page)).toEqual([]);
    await capture(page.getByRole('region', { name: 'Profile frontispiece', exact: true }), `private-${asset}-320`);
  }
  expectClean(result);
});
