import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { purgePrivateApiCaches } from './privacy';

const captured = vi.hoisted(() => ({ options: null }));
vi.mock('vite', () => ({ defineConfig: (config) => config }));
vi.mock('@vitejs/plugin-react', () => ({ default: () => ({}) }));
vi.mock('@tailwindcss/vite', () => ({ default: () => ({}) }));
vi.mock('@sentry/vite-plugin', () => ({ sentryVitePlugin: () => ({}) }));
vi.mock('vite-plugin-pwa', () => ({ VitePWA: (options) => { captured.options = options; return {}; } }));
import configureVite from '../../vite.config';

afterEach(() => vi.unstubAllGlobals());

function storage() {
  return {
    keys: vi.fn().mockResolvedValue(['api-reads', 'api-reads-v1', 'media-images', 'google-fonts', 'workbox-precache-v2']),
    delete: vi.fn().mockResolvedValue(true),
  };
}

describe('private API cache retirement', () => {
  it('removes only private response caches in the app', async () => {
    const caches = storage();
    vi.stubGlobal('caches', caches);
    await purgePrivateApiCaches();
    expect(caches.delete.mock.calls).toEqual([['api-reads'], ['api-reads-v1']]);
  });

  it('removes legacy private caches on worker activation and waits for deletion', async () => {
    const caches = storage();
    let activate;
    const source = readFileSync('public/privacy-sw.js', 'utf8');
    runInNewContext(source, { caches, self: { addEventListener: (name, handler) => {
      expect(name).toBe('activate');
      activate = handler;
    } } });
    const waitUntil = vi.fn();
    activate({ waitUntil });
    await waitUntil.mock.calls[0][0];
    expect(caches.delete.mock.calls).toEqual([['api-reads'], ['api-reads-v1']]);
  });

  it('does not register a private API cache route and preserves offline media/fonts', () => {
    configureVite({ command: 'serve' });
    const workbox = captured.options.workbox;
    expect(workbox.importScripts).toContain('/privacy-sw.js');
    const input = { sameOrigin: true, url: new URL('https://abby.example/api/auth/me/'), request: { destination: '' } };
    const routes = workbox.runtimeCaching;
    expect(routes.some(({ urlPattern }) => typeof urlPattern === 'function'
      ? urlPattern(input) : urlPattern.test(input.url.href))).toBe(false);
    expect(routes.map((route) => route.options.cacheName)).toEqual(['media-images', 'google-fonts']);
    expect(workbox.globPatterns).toContain('**/*.{js,css,html,svg,png,woff2,ttf}');
  });

  it('degrades when Cache Storage is unavailable or blocked', async () => {
    vi.stubGlobal('caches', undefined);
    await expect(purgePrivateApiCaches()).resolves.toBeUndefined();
    vi.stubGlobal('caches', { keys: vi.fn().mockRejectedValue(new Error('denied')) });
    await expect(purgePrivateApiCaches()).resolves.toBeUndefined();
  });
});
