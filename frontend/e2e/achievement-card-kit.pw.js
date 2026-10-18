import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

// Private release pixels must never enter hosted traces or test attachments.
// Deliberate local captures require an external, private evidence directory.
test.use({ trace: 'off', video: 'off', screenshot: 'off' });
const frontend = fileURLToPath(new URL('..', import.meta.url));
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const pin = lock.releases.find(release => release.family_id === 'abby-achievement-card-kit');
const manifestFile = pin && resolve(frontend, 'src/avatar/shared', pin.directory, 'manifest.json');
const manifest = manifestFile && existsSync(manifestFile) ? JSON.parse(readFileSync(manifestFile, 'utf8')) : null;
const evidence = process.env.ABBY_PRIVATE_ACCEPTANCE_DIR;
if (evidence && (!isAbsolute(evidence) || !relative(resolve(frontend, '..'), resolve(evidence)).startsWith('..'))) {
  throw new Error('ABBY_PRIVATE_ACCEPTANCE_DIR must be an absolute private directory outside the checkout.');
}
let server, origin;
const configuredPages = new WeakMap();

test.beforeAll(async () => {
  server = spawn(process.execPath, [resolve(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '0'], {
    cwd: frontend,
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolveOrigin, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Achievement acceptance server startup timed out.')), 30_000);
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Achievement acceptance server exited ${code}.`)); });
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

async function open(page, options = {}) {
  let errors = configuredPages.get(page);
  if (!errors) {
    errors = [];
    configuredPages.set(page, errors);
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) return route.abort('blockedbyclient');
      if (url.pathname.startsWith('/api/')) return route.fulfill({ json: [] });
      if (url.pathname.startsWith('/synthetic/')) {
        const color = url.pathname.includes('fish') ? '#8473AE' : '#D8AE65';
        return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><circle cx="128" cy="128" r="104" fill="${color}"/></svg>` });
      }
      return route.fallback();
    });
  }
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/achievement-card-kit-fixture.html?${new URLSearchParams(options)}`);
  await expect(page.locator('[data-kit-fixture]')).toBeVisible();
  return errors;
}

async function capture(page, name) {
  if (!evidence) return;
  mkdirSync(evidence, { recursive: true, mode: 0o700 });
  await page.screenshot({ path: resolve(evidence, `${name}.png`), animations: 'disabled' });
}

async function contentFits(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const overflow = await page.locator('.achievement-card__content').evaluateAll(elements => elements.flatMap(element => {
    const outer = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    const bounds = { left: outer.left + parseFloat(style.paddingLeft), right: outer.right - parseFloat(style.paddingRight), top: outer.top + parseFloat(style.paddingTop), bottom: outer.bottom - parseFloat(style.paddingBottom) };
    const issues = [];
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!node.textContent.trim() || node.parentElement.closest('[aria-hidden="true"]')) continue;
      if (getComputedStyle(node.parentElement).visibility === 'hidden') continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of range.getClientRects()) {
        if (!rect.width || !rect.height) continue;
        if (rect.left < bounds.left - 2 || rect.right > bounds.right + 2 || rect.top < bounds.top - 2 || rect.bottom > bounds.bottom + 2) {
          issues.push({ text: node.textContent.trim(), bounds: { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom }, rect: { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom } });
        }
      }
    }
    return issues;
  }));
  expect(overflow, 'Every live text line must remain inside its card content-safe region.').toEqual([]);
  const statsOverflow = await page.getByRole('region', { name: 'Profile achievement' }).locator('dl > div').evaluateAll(columns => columns.flatMap(column => {
    const bounds = column.getBoundingClientRect();
    const walker = document.createTreeWalker(column, NodeFilter.SHOW_TEXT);
    const issues = [];
    while (walker.nextNode()) {
      if (!walker.currentNode.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(walker.currentNode);
      for (const rect of range.getClientRects()) if (rect.left < bounds.left - 2 || rect.right > bounds.right + 2) issues.push(walker.currentNode.textContent.trim());
    }
    return issues;
  }));
  expect(statsOverflow, 'Actual Profile statistics must not overlap adjacent columns.').toEqual([]);
}

for (const theme of ['hyrule', 'vigil']) {
  test(`real Profile, collection, challenge and reward content reflows on ${theme}`, async ({ page }) => {
    for (const width of [320, 375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const large of ['0', '1']) {
        await test.step(`${width}px with ${large === '1' ? '200%' : '100%'} text`, async () => {
        const errors = await open(page, { theme, long: '1', large });
        await expect(page.locator('[data-achievement-card="wide"]')).toHaveCount(1);
        expect(await page.locator('[data-achievement-card="tall"]').count()).toBeGreaterThanOrEqual(6);
        await contentFits(page);
        const trophy = await page.locator('[data-trophy-slot]').evaluate(element => {
          const content = element.querySelector('.achievement-card__content');
          const style = getComputedStyle(content);
          const copy = element.querySelector('[data-trophy-copy]').getBoundingClientRect();
          const icon = element.querySelector('[data-badge-artwork]').getBoundingClientRect();
          return { available: content.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight), copy: { x: copy.x, y: copy.y, width: copy.width }, icon: { right: icon.right, y: icon.y, bottom: icon.bottom } };
        });
        if (large === '0' && trophy.available >= 194) {
          expect(trophy.copy.y, 'Compact normal-size trophy copy shares the icon row.').toBeCloseTo(trophy.icon.y, 0);
          expect(trophy.copy.x).toBeGreaterThan(trophy.icon.right);
        }
        if (large === '1' && width === 320) {
          expect(trophy.copy.y, 'Enlarged copy stacks below the badge icon.').toBeGreaterThan(trophy.icon.bottom);
          expect(trophy.copy.width).toBeCloseTo(trophy.available, 0);
        }
        // Badge identity remains the saved badge's own icon. Generic kit
        // illustrations are a separate preview and never a badge substitute.
        await expect(page.getByRole('region', { name: 'Achievement collection' }).locator('[data-badge-artwork]')).toHaveText(['🦉', '🌻', '🐚']);
        await expect(page.locator('[data-achievement-card-icon]')).toHaveCount(0);
        const rewardIdentity = page.getByRole('region', { name: 'Reward cards' }).getByRole('img', { name: 'Fish', exact: true });
        await expect(rewardIdentity).toBeVisible();
        expect(await rewardIdentity.getAttribute('src')).not.toContain('abby-achievement-card-kit');
        if (large === '0' || width === 320) await capture(page, `consumers-${theme}-${width}-${large === '1' ? '200' : '100'}`);
        expect(errors).toEqual([]);
        });
      }
    }
  });
}

test('live trophy, collection, challenge and reward actions remain usable with the new canvases', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 });
  const errors = await open(page);
  await page.getByRole('button', { name: /Trophy badge: Thoughtful creator/ }).click();
  const picker = page.getByRole('dialog', { name: 'Choose your trophy badge' });
  await expect(picker).toBeVisible();
  await picker.getByRole('button', { name: 'Helpful planner · rare', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('Choose trophy 82');
  await page.getByRole('button', { name: /Trophy badge: Helpful planner/ }).click();
  await picker.getByRole('button', { name: 'Helpful planner · rare', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('Clear trophy');
  await expect(page.getByRole('button', { name: /No trophy badge chosen/ })).toBeEnabled();
  await page.getByRole('region', { name: 'Achievement collection' }).getByRole('button', { name: 'Future creator · epic · not yet earned', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('View badge 83');
  await page.getByRole('button', { name: 'View Build a woodland garden', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('View challenge');
  await page.getByRole('button', { name: 'Pin to Today', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('Pin challenge');
  await page.getByRole('button', { name: 'Unpin', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('Unpin challenge');
  await page.getByRole('button', { name: 'Request reward', exact: true }).first().click();
  await expect(page.locator('[data-kit-event]')).toHaveText('Request reward 21');
  await page.getByRole('button', { name: 'Add Family movie night to wishlist', exact: true }).click();
  await expect(page.locator('[data-kit-event]')).toHaveText('Wishlist reward 21');
  expect(errors).toEqual([]);
});

test('unavailable or failed card artwork retains complete live content and controls', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 });
  await page.route(url => url.pathname.includes('/abby-achievement-card-kit/') && url.pathname.endsWith('.png'), route => route.request().resourceType() === 'image' ? route.abort() : route.fallback());
  const errors = await open(page, { mode: 'shapes', long: '1', large: '1', theme: 'vigil' });
  for (const variant of ['wide', 'tall']) {
    await expect(page.locator(`[data-kit-shape="${variant}"]`)).toHaveAttribute('data-achievement-card-art', 'unavailable');
    const button = page.getByRole('button', { name: `Continue ${variant}`, exact: true });
    await button.focus();
    await button.press('Enter');
    await expect(page.locator('[data-kit-event]')).toHaveText(`Continue ${variant}`);
  }
  await contentFits(page);
  await capture(page, 'failed-art-dark-320-200');
  expect(errors).toEqual([]);
});

test('matching native PNG pairs preserve 64px corner slices and scaled 96px safe insets', async ({ page }) => {
  test.skip(!manifest, 'Exact private release absent; real canvas and transparency acceptance remains pending.');
  const errors = await open(page, { mode: 'shapes', long: '1', large: '1' });
  for (const width of [320, 375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const variant of ['wide', 'tall']) {
      const card = page.locator(`[data-kit-shape="${variant}"]`);
      await expect(card).toHaveAttribute('data-achievement-card-art', 'ready');
      const geometry = await card.evaluate(element => {
        const bounds = element.getBoundingClientRect();
        const content = element.querySelector('.achievement-card__content');
        const style = getComputedStyle(content);
        return { width: bounds.width, height: bounds.height, pixelRatio: devicePixelRatio, insets: [style.paddingLeft, style.paddingTop, style.paddingRight, style.paddingBottom].map(value => parseFloat(value)),
          images: [...element.querySelectorAll('img')].map(image => ({ width: image.naturalWidth, height: image.naturalHeight, src: image.currentSrc })),
          layers: [...element.querySelectorAll('[data-achievement-card-layer]')].map(layer => ({ slice: getComputedStyle(layer).borderImageSlice, width: getComputedStyle(layer).borderTopWidth, source: getComputedStyle(layer).borderImageSource, repeat: getComputedStyle(layer).borderImageRepeat })),
        };
      });
      expect(geometry.images).toHaveLength(2);
      expect(geometry.images.map(image => [image.width, image.height])).toEqual([[1024, variant === 'wide' ? 512 : 1280], [1024, variant === 'wide' ? 512 : 1280]]);
      expect(new Set(geometry.images.map(image => image.src)).size).toBe(2);
      for (const inset of geometry.insets) expect(inset).toBeCloseTo(geometry.width * 96 / 1024, 0);
      expect(geometry.layers).toHaveLength(2);
      expect(new Set(geometry.layers.map(layer => layer.width)).size, 'Matching layers use identical rendered corner widths.').toBe(1);
      for (const layer of geometry.layers) {
        expect(layer.slice).toMatch(/^64(?: fill)?$/);
        // Engines snap border widths to device pixels; WebKit floors a
        // 17.5px declaration to 17px at DPR 1. Keep one physical pixel only.
        expect(Math.abs(Number.parseFloat(layer.width) - geometry.width * 64 / 1024)).toBeLessThanOrEqual(1 / geometry.pixelRatio);
        expect(layer.repeat).toBe('stretch');
      }
      // Sample original alpha in-browser, before compositing over page colors.
      const alpha = await card.locator('img').evaluateAll(images => images.map(image => {
        const canvas = document.createElement('canvas');
        canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        context.drawImage(image, 0, 0);
        const bytes = context.getImageData(0, 0, canvas.width, canvas.height).data;
        let transparent = 0, opaque = 0;
        for (let index = 3; index < bytes.length; index += 4) { if (bytes[index] === 0) transparent += 1; if (bytes[index] === 255) opaque += 1; }
        return { transparent, opaque, corners: [bytes[3], bytes[(canvas.width - 1) * 4 + 3], bytes[((canvas.height - 1) * canvas.width) * 4 + 3], bytes[(canvas.width * canvas.height - 1) * 4 + 3]], center: bytes[(Math.floor(canvas.height / 2) * canvas.width + Math.floor(canvas.width / 2)) * 4 + 3] };
      }));
      expect(alpha.every(image => image.transparent > 0 && image.opaque > 0)).toBe(true);
      expect(alpha.map(image => image.corners)).toEqual([[0, 0, 0, 0], [0, 0, 0, 0]]);
      expect(alpha[1].center, 'Gold overlay center remains transparent.').toBe(0);
    }
    await contentFits(page);
    await capture(page, `native-pairs-${width}-200`);
  }
  expect(errors).toEqual([]);
});

test('all three generic icons decode smoothly at 24, 32, 40, 64 and 96 CSS pixels on both backgrounds', async ({ page }) => {
  test.skip(!manifest, 'Exact private release absent; real icon sizing acceptance remains pending.');
  await page.setViewportSize({ width: 375, height: 812 });
  for (const theme of ['hyrule', 'vigil']) {
    const errors = await open(page, { mode: 'icons', theme });
    for (const size of [24, 32, 40, 64, 96]) {
      const icons = page.getByRole('region', { name: `${size}px icons` }).locator('[data-achievement-card-icon]');
      await expect(icons).toHaveCount(3);
      const urls = [];
      for (const icon of await icons.all()) {
        await icon.scrollIntoViewIfNeeded();
        await expect.poll(() => icon.evaluate(element => (element.matches('img') ? element : element.querySelector('img'))?.naturalWidth)).toBe(512);
        await icon.evaluate(element => (element.matches('img') ? element : element.querySelector('img')).decode());
        const dimensions = await icon.evaluate(element => {
          const img = element.matches('img') ? element : element.querySelector('img');
          const canvas = document.createElement('canvas');
          canvas.width = canvas.height = 512;
          const context = canvas.getContext('2d', { willReadFrequently: true });
          context.drawImage(img, 0, 0);
          const bytes = context.getImageData(0, 0, 512, 512).data;
          let transparent = 0, visible = 0, alphaMax = 0;
          for (let index = 3; index < bytes.length; index += 4) { if (bytes[index] === 0) transparent += 1; else visible += 1; alphaMax = Math.max(alphaMax, bytes[index]); }
          return img && { width: img.naturalWidth, height: img.naturalHeight, renderedWidth: img.getBoundingClientRect().width, renderedHeight: img.getBoundingClientRect().height, fit: getComputedStyle(img).objectFit, rendering: getComputedStyle(img).imageRendering, src: img.currentSrc, transparent, visible, alphaMax,
            corners: [bytes[3], bytes[(512 - 1) * 4 + 3], bytes[((512 - 1) * 512) * 4 + 3], bytes[(512 * 512 - 1) * 4 + 3]] };
        });
        expect(dimensions).toMatchObject({ width: 512, height: 512, renderedWidth: size, renderedHeight: size, fit: 'contain', rendering: 'auto' });
        expect(dimensions.transparent).toBeGreaterThan(0);
        expect(dimensions.visible).toBeGreaterThan(0);
        // The pinned originals intentionally peak at alpha 254. Preserve their
        // supplied alpha instead of flattening them or forcing opaque pixels.
        expect(dimensions.alphaMax).toBe(254);
        expect(dimensions.corners).toEqual([0, 0, 0, 0]);
        urls.push(dimensions.src);
      }
      expect(new Set(urls).size).toBe(3);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await capture(page, `icon-sizes-${theme}`);
    expect(errors).toEqual([]);
  }
});

test('loaded light parchment retains readable live text and action colors in both covers', async ({ page }) => {
  test.skip(!manifest, 'Exact private release absent; composited parchment contrast acceptance remains pending.');
  await page.setViewportSize({ width: 375, height: 812 });
  for (const theme of ['hyrule', 'vigil']) {
    await open(page, { theme });
    const cards = page.locator('[data-achievement-card]');
    await expect.poll(() => cards.evaluateAll(elements => elements.every(element => element.dataset.achievementCardArt === 'ready'))).toBe(true);
    // Loaded art swaps in a fixed light palette. Existing transition-colors
    // controls can briefly interpolate from the cover palette; measure their
    // settled, rendered state after the real transitions finish.
    await cards.evaluateAll(elements => Promise.all(elements.flatMap(element => element.getAnimations({ subtree: true })).map(animation => animation.finished.catch(() => undefined))));
    const results = await cards.evaluateAll(elements => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      const rgba = color => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = color;
        context.fillRect(0, 0, 1, 1);
        return [...context.getImageData(0, 0, 1, 1).data].map((value, index) => index === 3 ? value / 255 : value);
      };
      const composite = (front, back) => [...front.slice(0, 3).map((value, index) => value * front[3] + back[index] * (1 - front[3])), 1];
      const luminance = color => color.slice(0, 3).map(channel => channel / 255).map(channel => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
      const checks = [];
      for (const card of elements) {
        const image = card.querySelector('img');
        context.clearRect(0, 0, 1, 1);
        context.drawImage(image, Math.floor(image.naturalWidth / 2), Math.floor(image.naturalHeight / 2), 1, 1, 0, 0, 1, 1);
        const parchment = [...context.getImageData(0, 0, 1, 1).data].map((value, index) => index === 3 ? value / 255 : value);
        const walker = document.createTreeWalker(card.querySelector('.achievement-card__content'), NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (!/[\p{L}\p{N}]/u.test(node.textContent) || node.parentElement.closest('[aria-hidden="true"]')) continue;
          if (node.parentElement.closest('button:disabled, [aria-disabled="true"]')) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          if (![...range.getClientRects()].some(rect => rect.width && rect.height)) continue;
          const ancestry = [];
          for (let current = node.parentElement; current && current !== card; current = current.parentElement) ancestry.push(current);
          let background = parchment;
          for (const ancestor of ancestry.reverse()) background = composite(rgba(getComputedStyle(ancestor).backgroundColor), background);
          const foreground = composite(rgba(getComputedStyle(node.parentElement).color), background);
          const levels = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
          const ratio = (levels[1] + 0.05) / (levels[0] + 0.05);
          checks.push({ text: node.textContent.trim(), ratio, foreground, background });
        }
      }
      return { failures: checks.filter(check => check.ratio < 4.5), minimum: Math.min(...checks.map(check => check.ratio)), checks };
    });
    expect(results.failures, 'Live card text, including enabled controls, must retain 4.5:1 contrast over the real parchment sample.').toEqual([]);
    if (evidence) {
      mkdirSync(evidence, { recursive: true, mode: 0o700 });
      writeFileSync(resolve(evidence, `contrast-${theme}.json`), JSON.stringify(results, null, 2), { mode: 0o600 });
    }
  }
});
