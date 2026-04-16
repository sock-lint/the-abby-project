import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as Sentry from '@sentry/react';
import { server } from '../test/server.js';
import { api, getBlob, getToken, setToken } from './client.js';

describe('token helpers', () => {
  it('returns empty string when no token is stored', () => {
    expect(getToken()).toBe('');
  });

  it('persists and retrieves a token via localStorage', () => {
    setToken('abc123');
    expect(getToken()).toBe('abc123');
    expect(localStorage.getItem('abby_auth_token')).toBe('abc123');
  });

  it('clears the token when called with a falsy value', () => {
    setToken('abc');
    setToken(null);
    expect(getToken()).toBe('');
    setToken('');
    expect(getToken()).toBe('');
  });
});

describe('api.get', () => {
  it('returns parsed JSON from a 200 response', async () => {
    server.use(
      http.get('*/api/ping/', () => HttpResponse.json({ pong: true })),
    );
    await expect(api.get('/ping/')).resolves.toEqual({ pong: true });
  });

  it('sends the Authorization header when a token is present', async () => {
    setToken('tok');
    let captured;
    server.use(
      http.get('*/api/auth-check/', ({ request }) => {
        captured = request.headers.get('authorization');
        return HttpResponse.json({});
      }),
    );
    await api.get('/auth-check/');
    expect(captured).toBe('Token tok');
  });

  it('returns null for 204 No Content responses', async () => {
    server.use(
      http.get('*/api/empty/', () => new HttpResponse(null, { status: 204 })),
    );
    await expect(api.get('/empty/')).resolves.toBeNull();
  });
});

describe('api errors', () => {
  beforeEach(() => {
    Sentry.addBreadcrumb.mockClear();
    Sentry.captureException.mockClear();
  });

  it('uses error field from JSON error body', async () => {
    server.use(
      http.get('*/api/bad/', () =>
        HttpResponse.json({ error: 'nope' }, { status: 400 }),
      ),
    );
    await expect(api.get('/bad/')).rejects.toThrow('nope');
    expect(Sentry.addBreadcrumb).toHaveBeenCalled();
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('falls back to detail field', async () => {
    server.use(
      http.get('*/api/bad/', () =>
        HttpResponse.json({ detail: 'auth failed' }, { status: 401 }),
      ),
    );
    await expect(api.get('/bad/')).rejects.toThrow('auth failed');
  });

  it('falls back to serialized error body when neither error nor detail set', async () => {
    server.use(
      http.get('*/api/bad/', () =>
        HttpResponse.json({ field: ['bad'] }, { status: 400 }),
      ),
    );
    await expect(api.get('/bad/')).rejects.toThrow('{"field":["bad"]}');
  });

  it('falls back to statusText when body is not JSON', async () => {
    server.use(
      http.get('*/api/bad/', () => new HttpResponse('not json', { status: 400, statusText: 'Bad Request' })),
    );
    await expect(api.get('/bad/')).rejects.toThrow();
  });

  it('captures 5xx responses to Sentry', async () => {
    server.use(
      http.get('*/api/boom/', () =>
        HttpResponse.json({ error: 'boom' }, { status: 500 }),
      ),
    );
    await expect(api.get('/boom/')).rejects.toThrow('boom');
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
  });
});

describe('cache bypass', () => {
  it('sends cache: "no-store" on every request so disk-cached HTML errors can never poison the API surface', async () => {
    // Spy directly on fetch — MSW runs at the network layer and swallows the
    // fetch init object. We just want to verify the init the client builds.
    const realFetch = globalThis.fetch;
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve({}),
      }),
    );
    try {
      await api.get('/anything/');
      const init = fetchSpy.mock.calls.at(-1)[1];
      expect(init.cache).toBe('no-store');
    } finally {
      fetchSpy.mockRestore();
      globalThis.fetch = realFetch;
    }
  });
});

describe('non-JSON 200 guard', () => {
  beforeEach(() => {
    Sentry.addBreadcrumb.mockClear();
    Sentry.captureException.mockClear();
  });

  it('throws a clear error when a 200 response has HTML content-type (stale upstream error page)', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () =>
        new HttpResponse('<!DOCTYPE html><title>oops</title>', {
          status: 200,
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        }),
      ),
    );
    await expect(api.get('/notifications/unread_count/')).rejects.toThrow(
      /non-JSON response/i,
    );
    // Must surface to Sentry so we notice it happening in prod.
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
  });

  it('throws when the 200 response has no content-type at all', async () => {
    server.use(
      http.get('*/api/thing/', () =>
        // HttpResponse with a plain string body and explicit empty headers.
        new HttpResponse('not json', { status: 200, headers: {} }),
      ),
    );
    await expect(api.get('/thing/')).rejects.toThrow(/non-JSON response/i);
  });

  it('accepts application/json with a charset suffix', async () => {
    server.use(
      http.get('*/api/thing/', () =>
        new HttpResponse(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        }),
      ),
    );
    await expect(api.get('/thing/')).resolves.toEqual({ ok: true });
  });
});

describe('api.post / patch / delete', () => {
  it('stringifies a plain object body and sets JSON Content-Type', async () => {
    let seen;
    server.use(
      http.post('*/api/things/', async ({ request }) => {
        seen = {
          ct: request.headers.get('content-type'),
          body: await request.json(),
        };
        return HttpResponse.json({ id: 1 });
      }),
    );
    await api.post('/things/', { name: 'abby' });
    expect(seen.ct).toBe('application/json');
    expect(seen.body).toEqual({ name: 'abby' });
  });

  it('uploads FormData without a json Content-Type header', async () => {
    let contentType;
    server.use(
      http.post('*/api/upload/', ({ request }) => {
        contentType = request.headers.get('content-type') || '';
        return HttpResponse.json({ id: 1 });
      }),
    );
    const fd = new FormData();
    fd.append('file', new Blob(['x']));
    await api.upload('/upload/', fd);
    // FormData Content-Type is `multipart/form-data; boundary=...` — never
    // application/json.
    expect(contentType.startsWith('multipart/form-data')).toBe(true);
  });

  it('PATCHes via api.patch', async () => {
    let method;
    server.use(
      http.patch('*/api/things/1/', ({ request }) => {
        method = request.method;
        return HttpResponse.json({});
      }),
    );
    await api.patch('/things/1/', { name: 'x' });
    expect(method).toBe('PATCH');
  });

  it('DELETEs via api.delete', async () => {
    let method;
    server.use(
      http.delete('*/api/things/1/', ({ request }) => {
        method = request.method;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await api.delete('/things/1/');
    expect(method).toBe('DELETE');
  });
});

describe('getBlob', () => {
  afterEach(() => {
    Sentry.captureException.mockClear();
    Sentry.addBreadcrumb.mockClear();
  });

  it('returns a blob-like object on success', async () => {
    server.use(
      http.get('*/api/file/', () => new HttpResponse('binary-data')),
    );
    const blob = await getBlob('/file/');
    // jsdom and undici ship separate Blob classes, so instanceof is
    // unreliable. Duck-type the result instead.
    expect(typeof blob.size).toBe('number');
    expect(blob.size).toBe('binary-data'.length);
  });

  it('attaches Authorization when present', async () => {
    setToken('tok');
    let auth;
    server.use(
      http.get('*/api/file/', ({ request }) => {
        auth = request.headers.get('authorization');
        return new HttpResponse('binary-data');
      }),
    );
    await getBlob('/file/');
    expect(auth).toBe('Token tok');
  });

  it('throws and breadcrumbs on 4xx', async () => {
    server.use(
      http.get('*/api/file/', () => new HttpResponse(null, { status: 404, statusText: 'Not Found' })),
    );
    await expect(getBlob('/file/')).rejects.toThrow();
    expect(Sentry.addBreadcrumb).toHaveBeenCalled();
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('captures 5xx in Sentry', async () => {
    server.use(
      http.get('*/api/file/', () => new HttpResponse(null, { status: 500 })),
    );
    await expect(getBlob('/file/')).rejects.toThrow();
    expect(Sentry.captureException).toHaveBeenCalled();
  });
});
