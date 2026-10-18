import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { buildParent } from '../src/test/factories.js';
import { draftId, metadata, draft, saved, plan, comparison } from '../src/test/contentWorkbenchFixtures.js';

let devServer;
let origin;
test.use({ actionTimeout: 15_000 });
test.beforeAll(async () => {
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Fixture startup timed out: ${output}`)), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    devServer.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});
test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

for (const [theme, width, height, enlarged] of [['hyrule', 320, 568, false], ['vigil', 390, 740, true], ['sunlit', 1280, 900, false]]) {
  test(`draft workflow stays usable on ${theme} at ${width}px${enlarged ? ' with enlarged text' : ''}`, async ({ page }) => {
    const browserErrors = [];
    page.on('pageerror', (error) => browserErrors.push(error.message));
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-browser-session'));
    let current = structuredClone(draft);
    const publications = [];
    const mutations = [];
    await page.route(`${origin}/api/**`, async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path === '/api/auth/me/') return route.fulfill({ json: buildParent() });
      if (path === '/api/rpg/content-workbench/') return route.fulfill({ json: { ...metadata, drafts: [current] } });
      if (path === `/api/rpg/content-workbench/drafts/${draftId}/` && request.method() === 'GET') return route.fulfill({ json: current });
      const body = request.postDataJSON();
      mutations.push({ path, body });
      if (request.method() === 'PATCH') { current = { ...current, revision: current.revision + 1, changes: body.changes }; return route.fulfill({ json: current }); }
      if (path.endsWith('/preview/')) { current = { ...current, preview: plan }; return route.fulfill({ json: current }); }
      if (path.endsWith('/simulate/')) return route.fulfill({ json: { ...comparison, revision: current.revision } });
      if (path.endsWith('/publish/')) { publications.push(body); current = { ...current, published_at: '2026-10-17T00:00:00Z' }; return route.fulfill({ json: current }); }
      return route.fulfill({ status: 404, json: { detail: 'Unexpected synthetic request.' } });
    });
    await page.goto(`${origin}/e2e/content-workbench-fixture.html?theme=${theme}`);
    if (enlarged) await page.addStyleTag({ content: 'html { font-size: 150%; }' });
    const draftControl = page.getByRole('combobox', { name: 'Open draft' });
    await draftControl.click();
    await page.getByRole('option', { name: 'Forest balance · revision 1' }).click();
    await page.getByRole('button', { name: /🌲 Forest reading/ }).click();
    await page.getByRole('spinbutton', { name: 'Coin reward', exact: true }).fill('25');
    await page.getByRole('button', { name: 'Save to draft' }).click();
    await expect(page.getByText(/Changes saved to draft/)).toBeVisible();
    expect(mutations[0].body).toEqual({ revision: 1, changes: saved.changes });
    await page.getByRole('button', { name: 'Preview changes and audit rewards' }).click();
    await page.getByRole('button', { name: 'Compare published and draft' }).click();
    await expect(page.getByRole('region', { name: 'Published and draft comparison' })).toBeVisible();
    const overflow = await page.evaluate(() => ({ width: innerWidth, actual: document.documentElement.scrollWidth, nodes: [...document.querySelectorAll('body *')].filter((node) => node.getBoundingClientRect().right > innerWidth).slice(0, 20).map((node) => ({ tag: node.tagName, text: node.textContent.slice(0, 80), class: node.className, right: node.getBoundingClientRect().right, width: node.getBoundingClientRect().width })) }));
    expect(overflow.actual, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.width);
    await page.getByRole('button', { name: 'Publish reviewed draft' }).click();
    const dialog = page.getByRole('alertdialog', { name: 'Publish this reviewed draft?' });
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('button', { name: 'Publish reviewed draft' })).toBeFocused();
    expect(publications).toHaveLength(0);
    await page.getByRole('button', { name: 'Publish reviewed draft' }).click();
    await page.getByRole('button', { name: 'Publish now' }).click();
    await expect(page.getByText(/Draft published/)).toBeVisible();
    expect(publications).toEqual([{ revision: 2, preview_id: 'plan-1', content_digest: 'abc123', confirmation: true }]);
    expect(browserErrors).toEqual([]);
    await page.screenshot({ path: `/tmp/rpg-workbench-${theme}-${width}.png`, fullPage: true });
  });
}
