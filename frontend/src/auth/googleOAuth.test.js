import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { getToken, setToken } from '../api/client';
import { STORAGE_KEYS } from '../constants/storage';
import {
  captureGoogleCallback, completeGoogleAuthorization, startGoogleAuthorization,
  takeGoogleLinkResult, __resetGoogleAuthorizationForTesting,
} from './googleOAuth';
import { GOOGLE_CODE, GOOGLE_STATE, GOOGLE_URL, interceptGoogleNavigation, prepareGoogleCallback } from '../test/googleAuthorization';

afterEach(() => { window.history.replaceState({}, '', '/'); vi.unstubAllEnvs(); vi.useRealTimers(); });

function exchange(response = { mode: 'login', token: 'google-session', user: { id: 22 } }) {
  const requests = [];
  server.use(http.post('*/api/auth/google/exchange/', async ({ request }) => {
    requests.push({ body: await request.json(), auth: request.headers.get('authorization'), url: window.location.href });
    return HttpResponse.json(response);
  }));
  return requests;
}

describe('Google browser proof transaction', () => {
  it('sends only a fresh S256 challenge on start and keeps the verifier out of URLs and localStorage', async () => {
    const requests = [];
    server.use(http.get('*/api/auth/google/login/', ({ request }) => {
      requests.push(request);
      return HttpResponse.json({ authorization_url: GOOGLE_URL, state: GOOGLE_STATE, expires_in: 600 });
    }));
    const navigation = interceptGoogleNavigation();
    try {
      await startGoogleAuthorization({ mode: 'login' });
      const pending = JSON.parse(sessionStorage.getItem('abby_google_authorization_v1'));
      const url = new URL(requests[0].url);
      const expected = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(pending.verifier)))))
        .replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
      expect(url.searchParams.get('code_challenge')).toBe(expected);
      expect(url.searchParams.get('code_challenge_method')).toBe('S256');
      expect(requests[0].headers.get('authorization')).toBeNull();
      expect(navigation.destinations).toEqual([GOOGLE_URL]);
      expect(url.href).not.toContain(pending.verifier);
      expect(JSON.stringify(localStorage)).not.toContain(pending.verifier);
      expect(JSON.stringify(pending)).not.toContain(getToken());
    } finally { navigation.restore(); }
  });

  it('binds parent linking to the captured credential and exact child target', async () => {
    const requests = [];
    server.use(http.get('*/api/auth/google/', ({ request }) => {
      requests.push(request);
      return HttpResponse.json({ authorization_url: GOOGLE_URL, state: GOOGLE_STATE, expires_in: 600 });
    }));
    const navigation = interceptGoogleNavigation();
    try {
      await startGoogleAuthorization({ mode: 'link', forUserId: 7, actor: { id: 1, family: { id: 2 } } });
      expect(new URL(requests[0].url).searchParams.get('for_user')).toBe('7');
      expect(requests[0].headers.get('authorization')).toBe('Token test-session');
      const pending = JSON.parse(sessionStorage.getItem('abby_google_authorization_v1'));
      expect(pending).toMatchObject({ actorId: 1, familyId: 2, targetId: 7 });
    } finally { navigation.restore(); }
  });

  it('scrubs the return before async exchange, sends the verifier only in the body, and redeems once', async () => {
    await prepareGoogleCallback();
    const requests = exchange();
    captureGoogleCallback();
    expect(window.location.hash).toBe('');
    expect(requests).toEqual([]);
    const [first, second] = await Promise.all([completeGoogleAuthorization(), completeGoogleAuthorization()]);
    expect(first).toEqual(second);
    expect(requests).toHaveLength(1);
    expect(requests[0].body).toEqual({ exchange_code: GOOGLE_CODE, code_verifier: expect.stringMatching(/^[A-Za-z0-9_-]{43}$/) });
    expect(requests[0].auth).toBeNull();
    expect(requests[0].url).not.toContain(GOOGLE_CODE);
    expect(getToken()).toBe('google-session');
    expect(sessionStorage.getItem('abby_google_authorization_v1')).toBeNull();
  });

  it('accepts a pre-request reload after URL scrubbing', async () => {
    await prepareGoogleCallback();
    captureGoogleCallback();
    __resetGoogleAuthorizationForTesting();
    const requests = exchange();
    await completeGoogleAuthorization();
    expect(requests).toHaveLength(1);
    expect(getToken()).toBe('google-session');
  });

  it('does not replay an uncertain exchange after process termination', async () => {
    await prepareGoogleCallback();
    captureGoogleCallback();
    const key = 'abby_google_authorization_v1';
    sessionStorage.setItem(key, JSON.stringify({ ...JSON.parse(sessionStorage.getItem(key)), phase: 'exchanging' }));
    __resetGoogleAuthorizationForTesting();
    const requests = exchange();
    const result = await completeGoogleAuthorization();
    expect(result.error).toMatch(/interrupted.*start again/i);
    expect(requests).toEqual([]);
    expect(getToken()).toBe('test-session');
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it.each(['missing', 'wrong-state', 'expired', 'backend', 'credential'])('rejects a %s browser transaction without sending the exchange', async (reason) => {
    await prepareGoogleCallback();
    const key = 'abby_google_authorization_v1';
    const pending = JSON.parse(sessionStorage.getItem(key));
    if (reason === 'missing') sessionStorage.clear();
    if (reason === 'wrong-state') window.history.replaceState({}, '', `/#google_exchange=${GOOGLE_CODE}&google_state=unrelated-state`);
    if (reason === 'expired') sessionStorage.setItem(key, JSON.stringify({ ...pending, expiresAt: Date.now() - 1 }));
    if (reason === 'backend') sessionStorage.setItem(key, JSON.stringify({ ...pending, backend: 'https://other.example/api/' }));
    if (reason === 'credential') setToken('new-account');
    const requests = exchange();
    const result = await completeGoogleAuthorization();
    expect(result.error).toMatch(/start again/i);
    expect(requests).toEqual([]);
    expect(getToken()).toBe(reason === 'credential' ? 'new-account' : 'test-session');
    expect(window.location.hash).toBe('');
  });

  it('ignores an exchange response after account switching, without logging out the new account', async () => {
    await prepareGoogleCallback();
    let finish;
    const seen = [];
    const logouts = [];
    server.use(
      http.post('*/api/auth/google/exchange/', () => new Promise((resolve) => {
        seen.push(true); finish = () => resolve(HttpResponse.json({ mode: 'login', token: 'late-google', user: { id: 22 } }));
      })),
      http.post('*/api/auth/', () => { logouts.push(true); return HttpResponse.json({}); }),
    );
    const pending = completeGoogleAuthorization();
    await vi.waitFor(() => expect(seen).toHaveLength(1));
    setToken('new-account');
    finish();
    expect(await pending).toBeNull();
    expect(getToken()).toBe('new-account');
    expect(logouts).toEqual([]);
  });

  it('preserves a newer start while a previous exchange response is delayed', async () => {
    await prepareGoogleCallback();
    let finish;
    const seen = [];
    server.use(http.post('*/api/auth/google/exchange/', () => new Promise((resolve) => {
      seen.push(true); finish = () => resolve(HttpResponse.json({ mode: 'login', token: 'late-google', user: { id: 22 } }));
    })));
    const pending = completeGoogleAuthorization();
    await vi.waitFor(() => expect(seen).toHaveLength(1));
    const navigation = interceptGoogleNavigation();
    try { await startGoogleAuthorization({ mode: 'login' }); } finally { navigation.restore(); }
    const newer = sessionStorage.getItem('abby_google_authorization_v1');
    finish();
    expect(await pending).toBeNull();
    expect(sessionStorage.getItem('abby_google_authorization_v1')).toBe(newer);
    expect(getToken()).toBe('test-session');
  });

  it('finishes a verified link with the captured token and a noncredential Settings notice', async () => {
    await prepareGoogleCallback({ mode: 'link', forUserId: 7 });
    const requests = exchange({ mode: 'link', linked: true });
    await completeGoogleAuthorization();
    expect(requests[0].auth).toBe('Token test-session');
    expect(getToken()).toBe('test-session');
    expect(window.location.pathname).toBe('/settings');
    expect(window.location.search).toBe('');
    expect(takeGoogleLinkResult()).toEqual({ token: 'test-session', error: '' });
    expect(takeGoogleLinkResult()).toBeNull();
  });

  it('handles provider cancellation without an exchange or session change', async () => {
    await prepareGoogleCallback({ mode: 'link' });
    window.history.replaceState({}, '', `/#google_error=denied&google_state=${GOOGLE_STATE}`);
    const requests = exchange();
    const result = await completeGoogleAuthorization();
    expect(result.error).toMatch(/cancelled or denied/i);
    expect(requests).toEqual([]);
    expect(getToken()).toBe('test-session');
    expect(takeGoogleLinkResult().error).toMatch(/cancelled or denied/i);
  });

  it('does not reflect an arbitrary provider error into the UI', async () => {
    await prepareGoogleCallback();
    window.history.replaceState({}, '', `/#google_error=private-provider-detail&google_state=${GOOGLE_STATE}`);
    const result = await completeGoogleAuthorization();
    expect(result.error).not.toContain('private-provider-detail');
    expect(window.location.hash).toBe('');
  });

  it('does not automatically retry a failed exchange and allows a fresh start', async () => {
    await prepareGoogleCallback();
    const seen = [];
    server.use(http.post('*/api/auth/google/exchange/', () => { seen.push(true); return HttpResponse.error(); }));
    expect((await completeGoogleAuthorization()).error).toMatch(/interrupted/i);
    expect((await completeGoogleAuthorization()).error).toMatch(/interrupted/i);
    expect(seen).toHaveLength(1);
    expect(getToken()).toBe('test-session');
    const navigation = interceptGoogleNavigation();
    try { await startGoogleAuthorization({ mode: 'login' }); expect(navigation.destinations).toHaveLength(1); } finally { navigation.restore(); }
  });

  it('strips legacy token URLs without installing them or discarding the current identity', async () => {
    localStorage.setItem(STORAGE_KEYS.CACHED_USER, 'current-private-snapshot');
    window.history.replaceState({}, '', '/?token=attacker-credential#private');
    const requests = exchange();
    captureGoogleCallback();
    expect(window.location.href).not.toMatch(/attacker|private/);
    await completeGoogleAuthorization();
    expect(getToken()).toBe('test-session');
    expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBe('current-private-snapshot');
    expect(requests).toEqual([]);
  });

  it('refuses a cross-origin backend before any OAuth request', async () => {
    vi.stubEnv('VITE_API_URL', 'https://api.other.example');
    const requests = [];
    server.use(http.get('*/api/auth/google/login/', () => { requests.push(true); return HttpResponse.json({}); }));
    await expect(startGoogleAuthorization({ mode: 'login' })).rejects.toThrow(/hosted browser app/i);
    expect(requests).toEqual([]);
  });

  it('refuses a native return even with an HTTPS backend', async () => {
    vi.stubEnv('VITE_NATIVE_BUILD', 'true');
    vi.stubEnv('VITE_API_URL', 'https://staging.example');
    await expect(startGoogleAuthorization({ mode: 'link' })).rejects.toThrow(/hosted browser app/i);
    expect(sessionStorage.getItem('abby_google_authorization_v1')).toBeNull();
  });

  it('renders an allowlisted business failure without retrying the exchange or changing accounts', async () => {
    await prepareGoogleCallback();
    const requests = [];
    server.use(http.post('*/api/auth/google/exchange/', () => {
      requests.push(true);
      return HttpResponse.json({ error: 'safe error', code: 'no_account' }, { status: 400 });
    }));
    expect((await completeGoogleAuthorization()).error).toMatch(/no linked google account/i);
    expect(requests).toHaveLength(1);
    expect(getToken()).toBe('test-session');
  });

  it('refuses a different provider redirect origin even behind a same-origin API proxy', async () => {
    server.use(http.get('*/api/auth/google/login/', () => HttpResponse.json({
      authorization_url: 'https://accounts.google.com/o/oauth2/auth?redirect_uri=https%3A%2F%2Fother.example%2Fapi%2Fauth%2Fgoogle%2Fcallback%2F',
      state: GOOGLE_STATE, expires_in: 600,
    })));
    const navigation = interceptGoogleNavigation();
    try {
      await expect(startGoogleAuthorization({ mode: 'login' })).rejects.toThrow(/hosted browser app/i);
      expect(navigation.destinations).toEqual([]);
      expect(sessionStorage.getItem('abby_google_authorization_v1')).toBeNull();
    } finally { navigation.restore(); }
  });

  it('fails closed when browser session storage is denied', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Denied', 'SecurityError'); });
    try { await expect(startGoogleAuthorization({ mode: 'login' })).rejects.toThrow(/session storage/i); }
    finally { storage.mockRestore(); }
  });
});
