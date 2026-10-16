import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { assertDesignUx } from './live-smoke/design-ux.js';

test.use({ serviceWorkers: 'block', trace: 'off', screenshot: 'off', video: 'off' });

let devServer;
let origin;
test.beforeAll(async () => {
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Local gallery startup timeout')), 30_000);
    devServer.once('error', error => { clearTimeout(timer); reject(error); });
    devServer.once('exit', code => { clearTimeout(timer); reject(new Error(`Local gallery exited ${code}`)); });
    devServer.stdout.on('data', chunk => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
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

async function isolated(page) {
  const unexpected = [];
  await page.route('**/*', route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin || url.pathname.startsWith('/api/') || !['GET', 'HEAD'].includes(request.method())) {
      unexpected.push({ method: request.method(), path: url.pathname });
      return route.abort();
    }
    return route.continue();
  });
  return unexpected;
}

test('trusted design helper verifies the real anonymous gallery without product requests', async ({ page }) => {
  const unexpected = await isolated(page);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const result = await assertDesignUx(page, origin, { designPath: '/e2e/design-gallery-fixture.html' });
  expect(result).toEqual({ designMobile: true, themes: true, controlContrast: true, dialogKeyboard: true, attachments: true, motion: true });
  expect(page.viewportSize()).toEqual({ width: 1280, height: 800 });
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});

test('trusted design helper rejects unreadable rendered controls', async ({ page }) => {
  const unexpected = await isolated(page);
  // Deliberate DOM-only fixture damage proves the helper is measuring rendered
  // colors, rather than trusting the theme name or a hardcoded pass flag.
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = 'select, [role="combobox"] { color: black !important; background-color: black !important; }';
      document.head.appendChild(style);
    });
  });
  await expect(assertDesignUx(page, origin, { designPath: '/e2e/design-gallery-fixture.html' })).rejects.toThrow('DESIGN_CONTROL_CONTRAST');
  expect(unexpected).toEqual([]);
});

test('trusted design helper waits for finite theme and focus color transitions', async ({ page }) => {
  const unexpected = await isolated(page);
  // Preserve the real colors and transition properties, extending only the
  // duration to reproduce fast CI sampling of an intermediate painted color.
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = '.transition-colors { transition-duration: 600ms !important; transition-timing-function: linear !important; }';
      document.head.appendChild(style);
    });
  });
  const result = await assertDesignUx(page, origin, { designPath: '/e2e/design-gallery-fixture.html' });
  expect(result.controlContrast).toBe(true);
  expect(unexpected).toEqual([]);
});
