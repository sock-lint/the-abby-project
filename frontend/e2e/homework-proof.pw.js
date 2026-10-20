import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;

test.beforeAll(async () => {
  // This local fixture has no backend, account, or inherited app environment.
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

for (const viewport of [{ width: 320, height: 568 }, { width: 1280, height: 800 }]) {
  for (const theme of ['hyrule', 'vigil', 'sunlit', 'snowquill', 'verdant', 'harvest']) {
    test(`link-only homework proof fits ${viewport.width}px on ${theme}`, async ({ page }) => {
      const writes = [];
      const unexpected = [];
      await page.route('**/*', async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.origin !== origin) {
          unexpected.push(request.url());
          return route.abort();
        }
        if (url.pathname === '/api/homework/42/submit/' && request.method() === 'POST') {
          const form = await new Request(request.url(), {
            method: 'POST', headers: request.headers(), body: request.postDataBuffer(),
          }).formData();
          writes.push({ url, headers: request.headers(), fields: [...form.entries()] });
          return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({
            id: 9, status: 'pending', proof_url: form.get('proof_url'), proofs: [],
          }) });
        }
        if (url.pathname.startsWith('/api/')) {
          unexpected.push(request.url());
          return route.abort();
        }
        return route.continue();
      });
      await page.setViewportSize(viewport);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`${origin}/e2e/homework-proof-fixture.html?theme=${theme}`);
      const proof = page.getByRole('link', { name: /open proof link/i });
      await expect(proof).toBeVisible();
      const proofUrl = await proof.getAttribute('href');
      expect(new URL(proofUrl).searchParams.get('usp')).toBe('sharing');
      expect(new URL(proofUrl).hash).toBe('#page=2');
      await expect(proof).toHaveAttribute('target', '_blank');
      await expect(proof).toHaveAttribute('rel', 'noopener noreferrer');
      expect((await proof.boundingBox()).height).toBeGreaterThanOrEqual(44);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

      await page.getByRole('button', { name: 'Submit homework proof' }).click();
      const dialog = page.getByRole('dialog', { name: 'Submit homework' });
      await expect(dialog).toBeVisible();
      const submit = dialog.getByRole('button', { name: 'Submit for review' });
      await expect(submit).toBeDisabled();
      const input = dialog.getByRole('textbox', { name: 'Proof link (optional)' });
      await input.fill(proofUrl);
      await expect(input).toHaveValue(proofUrl);
      await expect(submit).toBeEnabled();
      await submit.scrollIntoViewIfNeeded();
      await expect(submit).toBeInViewport();
      const bounds = await submit.boundingBox();
      expect(bounds.height).toBeGreaterThanOrEqual(44);
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
      expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(dialog.locator('img')).toHaveCount(0);
      await submit.click();

      await expect(page.getByRole('status')).toHaveText('Homework submitted for review.');
      await expect(dialog).not.toBeVisible();
      expect(writes).toHaveLength(1);
      expect(writes[0].url.pathname).toBe('/api/homework/42/submit/');
      expect(writes[0].url.search).toBe('');
      expect(writes[0].headers['content-type']).toMatch(/^multipart\/form-data; boundary=/);
      expect(writes[0].headers.authorization).toBeUndefined();
      expect(writes[0].fields).toEqual([['proof_url', proofUrl]]);
      await expect(proof).toHaveAttribute('href', proofUrl);
      expect(unexpected).toEqual([]);
    });
  }
}
