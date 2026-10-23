import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;

test.beforeAll(async () => {
  devServer = spawn(process.execPath, [
    fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)),
    '--host', '127.0.0.1', '--port', '0',
  ], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  origin = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Vite fixture startup timed out: ${output}`)), 30_000);
    devServer.once('error', error => { clearTimeout(timer); reject(error); });
    devServer.once('exit', code => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    devServer.stdout.on('data', chunk => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    devServer.stderr.on('data', chunk => { output += chunk.toString(); });
  });
});

test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

test('Atlas specimens expose real names and local selection without account requests', async ({ page }) => {
  const accountRequests = [];
  // Match API paths, not Vite's /src/api/ client module.
  await page.route(url => url.pathname === '/api' || url.pathname.startsWith('/api/'), route => {
    accountRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html`);
  const atlas = page.getByRole('region', { name: 'Atlas primitives', exact: true });
  await expect(atlas).toBeVisible();
  await expect(page.getByRole('link', { name: 'Atlas primitives', exact: true })).toHaveAttribute('href', '#design-atlas');
  for (const rarity of ['common', 'uncommon', 'rare', 'epic', 'legendary']) {
    const name = `${rarity[0].toUpperCase()}${rarity.slice(1)} example badge`;
    await expect(atlas.getByRole('button', { name: `${name} · ${rarity}`, exact: true })).toBeVisible();
    await expect(atlas.getByRole('button', { name: `${name} · ${rarity} · not yet earned`, exact: true })).toBeVisible();
  }
  const locked = atlas.getByRole('button', { name: 'Rare example badge · rare · not yet earned', exact: true });
  await locked.focus();
  await page.keyboard.press('Enter');
  await expect(atlas.getByRole('status', { name: 'Badge selection', exact: true })).toHaveText('Selected preview: Rare example badge · rare · not yet earned.');
  await atlas.getByRole('checkbox', { name: 'Show badge unlock hints', exact: true }).uncheck();
  await expect(atlas.locator('[data-sigil-hint]')).toHaveCount(0);
  await atlas.getByRole('checkbox', { name: 'Show badge unlock hints', exact: true }).check();
  await expect(atlas.locator('[data-sigil-hint]')).toHaveCount(5);
  await atlas.getByRole('button', { name: 'Common example badge · common', exact: true }).click();
  await expect(atlas.getByRole('status', { name: 'Badge selection', exact: true })).toHaveText('Selected preview: Common example badge · common · earned.');
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(atlas.getByRole('heading', { name: 'Bare chapter example', level: 4, exact: true })).toBeVisible();
  await expect(atlas.getByRole('heading', { name: 'Direct chapter heading', level: 3, exact: true })).toBeVisible();
  await expect(atlas.getByRole('heading', { name: 'Legacy subject heading', level: 3, exact: true })).toBeVisible();
  await expect(atlas.getByRole('img', { name: 'no seals catalogued', exact: true })).toHaveCount(2);
  const docs = atlas.getByText('Usage and existing consumers', { exact: true });
  await docs.click();
  await expect(atlas.getByRole('link', { name: 'pages/achievements/CollectionFolio.jsx', exact: true })).toBeVisible();
  expect(accountRequests).toEqual([]);
});

test('Atlas long content reflows at 320px with enlarged text', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/design-gallery-fixture.html?theme=vigil`);
  await page.getByRole('checkbox', { name: 'Long content', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Larger text', exact: true }).check();
  await page.evaluate(() => document.fonts.ready);
  const atlas = page.getByRole('region', { name: 'Atlas primitives', exact: true });
  await expect(atlas).toBeVisible();
  await expect(atlas.getByText('Show badge unlock hints', { exact: true })).toHaveCSS('font-size', '20px');
  await expect(atlas.getByRole('heading', { level: 4 })).toHaveCount(3);
  await atlas.getByText('Usage and existing consumers', { exact: true }).click();
  const overflow = await atlas.evaluate(region => [...region.querySelectorAll('*')]
    .filter(element => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && (rect.left < 0 || rect.right > window.innerWidth + 0.5);
    }).map(element => ({ tag: element.tagName, text: element.textContent?.slice(0, 60) })));
  expect(overflow).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});
