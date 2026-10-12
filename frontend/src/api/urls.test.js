import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { apiUrl, backendMediaUrl } from './urls';
import { api } from './client';
import { fetchSpriteCatalog, getSkillCatalog } from './index';

afterEach(() => vi.unstubAllEnvs());

describe('configured API origin', () => {
  it('preserves same-origin web URLs', () => {
    vi.stubEnv('VITE_API_URL', '');
    vi.stubEnv('VITE_NATIVE_BUILD', '');
    expect(apiUrl('/auth/')).toBe('/api/auth/');
  });

  it('uses the explicit staging origin for private reads, mutations, sprites and pagination', async () => {
    vi.stubEnv('VITE_NATIVE_BUILD', 'true');
    vi.stubEnv('VITE_API_URL', 'https://staging.abby.example/');
    const requests = [];
    server.use(
      http.get('https://staging.abby.example/api/ping/', ({ request }) => {
        requests.push(new URL(request.url));
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json({ ok: true });
      }),
      http.post('https://staging.abby.example/api/ping/', async ({ request }) => {
        requests.push(new URL(request.url));
        expect(await request.json()).toEqual({ example: true });
        return HttpResponse.json({ ok: true });
      }),
      http.get('https://staging.abby.example/api/sprites/catalog/', ({ request }) => {
        requests.push(new URL(request.url));
        expect(request.headers.get('Authorization')).toBeNull();
        expect(request.headers.get('If-None-Match')).toBe('"sprite-etag"');
        return HttpResponse.json({ sprites: {}, etag: 'sprite-etag' });
      }),
      http.get('https://staging.abby.example/api/subjects/', ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        return HttpResponse.json({
          results: [{ id: url.searchParams.has('page') ? 2 : 1 }],
          next: url.searchParams.has('page') ? null : 'https://untrusted.example/api/subjects/?page=2',
        });
      }),
      http.get('https://staging.abby.example/api/skills/', ({ request }) => {
        requests.push(new URL(request.url));
        return HttpResponse.json([]);
      }),
    );
    await api.get('/ping/');
    await api.post('/ping/', { example: true });
    await fetchSpriteCatalog('sprite-etag');
    await expect(getSkillCatalog()).resolves.toEqual({ subjects: [{ id: 1 }, { id: 2 }], skills: [] });
    expect(requests).toHaveLength(6);
    expect(requests.every((url) => url.origin === 'https://staging.abby.example')).toBe(true);
    expect(requests[0].searchParams.get('_abby_session')).toBeTruthy();
  });

  it.each(['', 'http://staging.example', 'https://user:password@staging.example',
    'https://staging.example/api', 'https://staging.example/?token=secret'])('rejects unsafe native origin %s', (origin) => {
    vi.stubEnv('VITE_NATIVE_BUILD', 'true');
    vi.stubEnv('VITE_API_URL', origin);
    expect(() => apiUrl('/auth/')).toThrow();
  });

  it('rejects absolute paths supplied by callers', () => {
    expect(() => apiUrl('//other.example/auth/')).toThrow();
    expect(() => apiUrl('https://other.example/auth/')).toThrow();
  });

  it('resolves local Django media against the native backend and preserves signed asset URLs', () => {
    vi.stubEnv('VITE_NATIVE_BUILD', 'true');
    vi.stubEnv('VITE_API_URL', 'https://staging.abby.example');
    expect(backendMediaUrl('/media/rpg-sprites/chick.png')).toBe('https://staging.abby.example/media/rpg-sprites/chick.png');
    expect(backendMediaUrl('https://media.example/chick.png?signature=synthetic')).toBe('https://media.example/chick.png?signature=synthetic');
    expect(backendMediaUrl(null)).toBeNull();
    expect(backendMediaUrl('https://[invalid')).toBeNull();
    vi.stubEnv('VITE_NATIVE_BUILD', '');
    expect(backendMediaUrl('/media/rpg-sprites/chick.png')).toBe('/media/rpg-sprites/chick.png');
  });
});
