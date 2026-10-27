import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';
import * as apiIndex from '../api/index.js';
import { getToken, setToken } from '../api/client.js';
import { STORAGE_KEYS } from '../constants/storage.js';
import { prepareGoogleCallback } from '../test/googleAuthorization';
import * as Sentry from '@sentry/react';
import { GATEWAY_RETRY_DELAY_MS } from '../api/client.js';
import {
  AuthProvider, DEFERRED_RECOVERY_DELAY_MS, OFFLINE_MESSAGE, useApi, useAuth,
} from './useApi.js';

describe('useApi', () => {
  it('starts in loading state, then resolves data', async () => {
    const fn = vi.fn().mockResolvedValue({ value: 42 });
    const { result } = renderHook(() => useApi(fn, []));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ value: 42 });
    expect(result.current.error).toBeNull();
  });

  it('surfaces error messages', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(result.current.data).toBeNull();
  });

  it('reload() re-invokes the fn', async () => {
    let call = 0;
    const fn = vi.fn(async () => ({ n: ++call }));
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }));
    let confirmed;
    await act(async () => { confirmed = await result.current.reload(); });
    expect(result.current.data).toEqual({ n: 2 });
    expect(confirmed).toEqual({ n: 2 });
    expect(fn).toHaveBeenCalledTimes(2);
  });

  // Almost every page early-returns a full-page Loader/skeleton on `loading`,
  // so a reload() that raised it unmounted the page the action was fired from
  // — every habit tap and step toggle blanked the screen and lost scroll.
  it('reload() keeps loading false and holds the old data while re-fetching', async () => {
    let resolveSecond;
    let call = 0;
    const fn = vi.fn(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ n: 1 });
      return new Promise((res) => { resolveSecond = () => res({ n: 2 }); });
    });
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }));

    act(() => { result.current.reload(); });
    await waitFor(() => expect(result.current.refreshing).toBe(true));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toEqual({ n: 1 });

    await act(async () => { resolveSecond(); });
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    expect(result.current.data).toEqual({ n: 2 });
  });

  it('setData mutates locally without re-fetching', async () => {
    const fn = vi.fn().mockResolvedValue(1);
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.data).toBe(1));
    act(() => result.current.setData(99));
    expect(result.current.data).toBe(99);
  });

  it('setData accepts an updater and keeps reload() off the full-page loader', async () => {
    const fn = vi.fn().mockResolvedValue({ n: 1 });
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }));
    act(() => result.current.setData((prev) => ({ n: prev.n + 1 })));
    expect(result.current.data).toEqual({ n: 2 });
    await act(async () => { await result.current.reload(); });
    expect(result.current.loading).toBe(false);
  });

  // A dead connection used to render the browser's own wording inside
  // ErrorAlert — "Failed to fetch" on Chrome, "Load failed" on Safari — on
  // every page a kid opened without signal.
  it('translates a network failure into kid-readable copy', async () => {
    const fn = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.error).toBe(OFFLINE_MESSAGE));
    expect(result.current.error).not.toMatch(/failed to fetch/i);
  });

  it('translates Safari\'s "Load failed" wording too', async () => {
    const fn = vi.fn().mockRejectedValue(new TypeError('Load failed'));
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.error).toBe(OFFLINE_MESSAGE));
  });

  // api/client.js attaches .status to every HTTP error; those messages come
  // from the server and are already written for humans, so they pass through.
  it('keeps server error messages verbatim', async () => {
    const err = new Error('You already logged that today.');
    err.status = 409;
    const fn = vi.fn().mockRejectedValue(err);
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.error).toBe('You already logged that today.'));
  });

  it('silently ignores AbortError', async () => {
    const err = new Error('aborted');
    err.name = 'AbortError';
    const fn = vi.fn().mockRejectedValue(err);
    const { result } = renderHook(() => useApi(fn, []));
    // Loading may still flip because the finally block doesn't run when
    // the signal is aborted — but the error must never surface.
    await waitFor(() => expect(result.current.error).toBeNull(), { timeout: 50 });
    expect(result.current.error).toBeNull();
  });

  it('re-fetches when deps change', async () => {
    const fn = vi.fn(async (_signal) => fn.mock.calls.length);
    let dep = 'a';
    const { result, rerender } = renderHook(() => useApi(fn, [dep]));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    dep = 'b';
    rerender();
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    // waitFor: the call-count assertion above passes the moment the second
    // fetch STARTS (loading just flipped back to true) — the resolved state
    // lands a microtask later, which loses the race under a loaded CI run.
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('aborts in-flight requests on unmount', async () => {
    let abortedSignal = null;
    const fn = vi.fn((signal) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => {
        abortedSignal = signal;
        const err = new Error('abort');
        err.name = 'AbortError';
        reject(err);
      });
    }));
    const { unmount } = renderHook(() => useApi(fn, []));
    unmount();
    await waitFor(() => expect(abortedSignal?.aborted).toBe(true));
  });

  it('aborts a prior request when deps change before it completes', async () => {
    const signals = [];
    const fn = vi.fn((signal) => {
      signals.push(signal);
      return new Promise(() => {}); // never resolves
    });
    let dep = 'a';
    const { rerender } = renderHook(() => useApi(fn, [dep]));
    await waitFor(() => expect(signals).toHaveLength(1));
    dep = 'b';
    rerender();
    await waitFor(() => expect(signals).toHaveLength(2));
    expect(signals[0].aborted).toBe(true);
  });
});

describe('AuthProvider + useAuth', () => {
  it('clears only the deleted session and its cached identity without another logout request', async () => {
    setToken('deleted-account-session');
    const user = buildUser();
    const logout = vi.spyOn(apiIndex, 'logout');
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.user).toEqual(user));
    let cleared;
    act(() => { cleared = result.current.signOutDeletedAccount('deleted-account-session'); });
    expect(cleared).toBe(true);
    expect(getToken()).toBe('');
    expect(result.current.user).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
    expect(logout).not.toHaveBeenCalled();
    logout.mockRestore();
  });

  it('ignores deletion completion after a different account signs in', async () => {
    const newer = buildUser({ id: 702, username: 'replacement-account' });
    setToken('replacement-session');
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(newer)));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.user).toEqual(newer));
    const cached = localStorage.getItem(STORAGE_KEYS.CACHED_USER);
    let cleared;
    act(() => { cleared = result.current.signOutDeletedAccount('old-deleted-session'); });
    expect(cleared).toBe(false);
    expect(getToken()).toBe('replacement-session');
    expect(result.current.user).toEqual(newer);
    expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBe(cached);
  });

  it('does not unsubscribe a replacement account when deleted-session push teardown is delayed', async () => {
    const originalWorker = navigator.serviceWorker;
    let finishRegistration;
    const registration = new Promise((resolve) => { finishRegistration = resolve; });
    const getRegistration = vi.fn(() => registration);
    const unsubscribe = vi.fn(async () => true);
    const subscription = { endpoint: 'https://push.example.invalid/new-session', unsubscribe };
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { getRegistration } });
    try {
      setToken('deleted-push-session');
      const user = buildUser();
      server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
      const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
      await waitFor(() => expect(result.current.user).toEqual(user));
      act(() => result.current.signOutDeletedAccount('deleted-push-session'));
      await waitFor(() => expect(getRegistration).toHaveBeenCalledTimes(1));
      act(() => setToken('replacement-push-session'));
      await act(async () => {
        finishRegistration({ pushManager: { getSubscription: async () => subscription } });
        await registration;
      });
      expect(unsubscribe).not.toHaveBeenCalled();
      expect(getToken()).toBe('replacement-push-session');
    } finally {
      Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: originalWorker });
    }
  });

  it('throws if used outside the provider', () => {
    // renderHook's wrapper defaults to a no-op; useAuth should throw inside
    // the hook body.
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/);
  });

  it('fetches the current user on mount', async () => {
    const user = buildUser();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
    const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toEqual(user);
  });

  it('sets user to null when /me/ fails', async () => {
    server.use(
      http.get('*/api/auth/me/', () =>
        HttpResponse.json({ detail: 'nope' }, { status: 401 }),
      ),
    );
    const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it('stashes the user snapshot in localStorage on a successful boot fetch', async () => {
    const user = buildUser();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
    const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.offline).toBe(false);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEYS.CACHED_USER))).toEqual({ version: 2, token: 'test-session', user });
  });

  describe('offline boot hydration', () => {
    const cached = buildUser({ first_name: 'Cached' });

    it('recovers the live profile after an HTML proxy response instead of hydrating the offline snapshot', async () => {
      const token = 'proxy-recovery-session';
      const liveUser = buildUser({ id: 27, first_name: 'Live' });
      setToken(token);
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify({ version: 2, token, user: cached }));
      const requests = [];
      server.use(http.get('*/api/auth/me/', ({ request }) => {
        requests.push(request.headers.get('authorization'));
        if (requests.length === 1) {
          return new HttpResponse('<!DOCTYPE html><title>Oops — Something Broke</title>', {
            status: 200,
            headers: { 'Content-Type': 'text/html; charset=utf-8' },
          });
        }
        return HttpResponse.json(liveUser);
      }));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(requests).toEqual([`Token ${token}`, `Token ${token}`]);
      expect(result.current.user).toEqual(liveUser);
      expect(result.current.offline).toBe(false);
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe(token);
      expect(JSON.parse(localStorage.getItem(STORAGE_KEYS.CACHED_USER))).toEqual({
        version: 2, token, user: liveUser,
      });
    });

    it('hydrates from the cached user + flags offline when getMe network-errors and a token is present', async () => {
      localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'tok-123');
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify({ version: 2, token: 'tok-123', user: cached }));
      // HttpResponse.error() = a fetch/network rejection — the thrown error
      // has no .status, unlike HTTP errors from api/client.js.
      server.use(http.get('*/api/auth/me/', () => HttpResponse.error()));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.user).toEqual(cached);
      expect(result.current.offline).toBe(true);
    });

    it('does NOT hydrate on an HTTP rejection — a .status error keeps the logged-out path', async () => {
      localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'tok-123');
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify({ version: 2, token: 'tok-123', user: cached }));
      // 403 (not 401) so the api client's 401 self-heal reload stays out of
      // the picture; any err.status must skip the cache.
      server.use(
        http.get('*/api/auth/me/', () =>
          HttpResponse.json({ detail: 'forbidden' }, { status: 403 }),
        ),
      );
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.user).toBeNull();
      expect(result.current.offline).toBe(false);
    });

    it('does NOT hydrate without an auth token, even on a network error', async () => {
      setToken(null);
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify(cached));
      server.use(http.get('*/api/auth/me/', () => HttpResponse.error()));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.user).toBeNull();
      expect(result.current.offline).toBe(false);
    });

    it.each([
      ['legacy snapshot', cached],
      ['another credential', { version: 2, token: 'account-a', user: cached }],
    ])('rejects a %s when the new account is offline', async (_name, snapshot) => {
      setToken('account-b');
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify(snapshot));
      server.use(http.get('*/api/auth/me/', () => HttpResponse.error()));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.user).toBeNull();
      expect(result.current.offline).toBe(false);
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
    });

    it('cannot revive an anonymous session from a successful stale /me/ response', async () => {
      setToken(null);
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify({ version: 2, token: 'old-session', user: cached }));
      const getMe = vi.spyOn(apiIndex, 'getMe').mockResolvedValue(cached);
      try {
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(getMe).not.toHaveBeenCalled();
        expect(result.current.user).toBeNull();
        expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
      } finally { getMe.mockRestore(); }
    });

    it('purges legacy private API caches before fetching the current profile', async () => {
      const deleted = [];
      const previous = globalThis.caches;
      vi.stubGlobal('caches', {
        keys: vi.fn().mockResolvedValue(['api-reads', 'media-images']),
        delete: vi.fn(async (name) => { deleted.push(name); return true; }),
      });
      const getMe = vi.spyOn(apiIndex, 'getMe').mockImplementation(async () => {
        expect(deleted).toContain('api-reads');
        return cached;
      });
      try {
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(deleted).toEqual(['api-reads']);
      } finally { getMe.mockRestore(); vi.stubGlobal('caches', previous); }
    });

    it('clears the old parent identity before replacing it with an offline OAuth child token', async () => {
      setToken('parent-session');
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify({ version: 2, token: 'parent-session', user: cached }));
      await prepareGoogleCallback();
      server.use(http.post('*/api/auth/google/exchange/', () => HttpResponse.json({ mode: 'login', token: 'child-session', user: buildUser({ id: 2 }) })));
      server.use(http.get('*/api/auth/me/', ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Token child-session');
        expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
        return HttpResponse.error();
      }));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.user).toBeNull();
      expect(result.current.offline).toBe(false);
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('child-session');
      expect(window.location.search).toBe('');
    });

    it('finishes OAuth boot with a visible cleanup error when the old push endpoint cannot stop', async () => {
      setToken('oauth-push-account-a');
      localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify({ version: 2, token: 'oauth-push-account-a', user: cached }));
      await prepareGoogleCallback();
      server.use(http.post('*/api/auth/google/exchange/', () => HttpResponse.json({ mode: 'login', token: 'oauth-push-account-b', user: buildUser({ id: 2 }) })));
      const originalWorker = navigator.serviceWorker;
      Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
        getRegistration: vi.fn().mockResolvedValue({ pushManager: {
          getSubscription: vi.fn().mockResolvedValue({ endpoint: 'https://push.example/old', unsubscribe: vi.fn().mockResolvedValue(false) }),
        } }),
      } });
      server.use(http.post('*/api/push/unsubscribe/', () => HttpResponse.error()));
      const getMe = vi.spyOn(apiIndex, 'getMe').mockResolvedValue(buildUser({ id: 2 }));
      try {
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.sessionError).toMatch(/could not stop notifications/i);
        expect(result.current.user).toBeNull();
        expect(getMe).not.toHaveBeenCalled();
        expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('oauth-push-account-a');
        expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
      } finally {
        getMe.mockRestore();
        Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: originalWorker });
      }
    });

    it('restores only the account actually signed in before an offline reload', async () => {
      setToken('account-a');
      server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: 1, role: 'parent' }))));
      const accountB = buildUser({ id: 2, username: 'child-b', role: 'child', token: 'account-b' });
      server.use(http.post('*/api/auth/', async ({ request }) => {
        const body = await request.json();
        if (body.action === 'logout') return HttpResponse.json({ ok: true });
        expect(body).toEqual({ action: 'login', username: 'child-b', password: 'test-password' });
        return HttpResponse.json(accountB);
      }));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const first = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(first.result.current.user?.id).toBe(1));
      await act(async () => { await first.result.current.login('child-b', 'test-password'); });
      expect(first.result.current.user).toEqual(accountB);
      first.unmount();
      server.use(http.get('*/api/auth/me/', () => HttpResponse.error()));
      const next = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(next.result.current.loading).toBe(false));
      expect(next.result.current.user).toEqual(accountB);
      expect(next.result.current.offline).toBe(true);
    });
  });

  describe('login/logout callbacks', () => {
    let loginSpy;
    let logoutSpy;

    beforeEach(() => {
      loginSpy = vi.spyOn(apiIndex, 'login').mockResolvedValue(buildUser({ id: 7 }));
      logoutSpy = vi.spyOn(apiIndex, 'logout').mockResolvedValue();
    });

    afterEach(() => {
      loginSpy.mockRestore();
      logoutSpy.mockRestore();
    });

    it('login() updates user', async () => {
      server.use(
        http.get('*/api/auth/me/', () => HttpResponse.json(null, { status: 401 })),
      );
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      // wait for boot
      await waitFor(() => expect(result.current.loading).toBe(false));
      await act(async () => { await result.current.login('abby', 'x'); });
      expect(result.current.user).toEqual(buildUser({ id: 7 }));
      expect(loginSpy).toHaveBeenCalledWith('abby', 'x');
    });

    it('logout() clears user and the cached snapshot', async () => {
      server.use(
        http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      );
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.user).not.toBeNull());
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).not.toBeNull();
      await act(async () => { await result.current.logout(); });
      expect(result.current.user).toBeNull();
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
      expect(logoutSpy).toHaveBeenCalled();
    });

    it('a delayed logout does not clear a newer login or its cached user', async () => {
      setToken('old-session');
      server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));

      let finishLogout;
      logoutSpy.mockImplementationOnce(() => new Promise((resolve) => { finishLogout = resolve; }));
      const newerUser = buildUser({ id: 77, username: 'new-account' });
      loginSpy.mockImplementationOnce(async () => {
        setToken('new-session');
        return newerUser;
      });
      let pending;
      act(() => { pending = result.current.logout(); });
      await act(async () => { await result.current.login('new-account', 'synthetic-password'); });
      await act(async () => {
        finishLogout();
        await pending;
      });

      expect(result.current.user).toEqual(newerUser);
      expect(JSON.parse(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).user).toEqual(newerUser);
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('new-session');
    });
  });

  describe('shared browser session changes', () => {
    let originalLocation;
    let reloadSpy;

    beforeEach(() => {
      reloadSpy = vi.fn();
      originalLocation = window.location;
      Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: {
          href: originalLocation.href,
          origin: originalLocation.origin,
          protocol: originalLocation.protocol,
          host: originalLocation.host,
          hostname: originalLocation.hostname,
          port: originalLocation.port,
          pathname: originalLocation.pathname,
          search: originalLocation.search,
          hash: originalLocation.hash,
          reload: reloadSpy,
        },
      });
      setToken('old-session');
      server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    });

    afterEach(() => {
      Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: originalLocation,
      });
    });

    it.each(['new-session', null])('reloads after another tab changes auth to %s', async (newToken) => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).not.toBeNull();

      setToken(newToken);
      act(() => window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEYS.AUTH_TOKEN,
        oldValue: 'old-session',
        newValue: newToken,
        storageArea: localStorage,
      })));

      await waitFor(() => expect(reloadSpy).toHaveBeenCalledTimes(1));
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe(newToken);
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
    });

    it('reloads after another tab clears localStorage', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      localStorage.clear();
      act(() => window.dispatchEvent(new StorageEvent('storage', { storageArea: localStorage })));
      await waitFor(() => expect(reloadSpy).toHaveBeenCalledTimes(1));
    });

    it('does not repopulate the old user cache from a delayed boot response', async () => {
      let releaseResponse;
      let signalStarted;
      const started = new Promise((resolve) => { signalStarted = resolve; });
      const responseReady = new Promise((resolve) => { releaseResponse = resolve; });
      server.use(http.get('*/api/auth/me/', async () => {
        signalStarted();
        await responseReady;
        return HttpResponse.json(buildUser());
      }));
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await started;
      setToken('new-session');
      act(() => window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEYS.AUTH_TOKEN, oldValue: 'old-session', newValue: 'new-session', storageArea: localStorage,
      })));
      await act(async () => { releaseResponse(); });
      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.user).toBeNull();
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBeNull();
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('new-session');
    });

    it('ignores unrelated, unchanged, or sessionStorage events and detaches on unmount', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result, unmount } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.loading).toBe(false));
      const cachedUser = localStorage.getItem(STORAGE_KEYS.CACHED_USER);
      act(() => {
        window.dispatchEvent(new StorageEvent('storage', {
          key: STORAGE_KEYS.CACHED_USER, oldValue: null, newValue: cachedUser, storageArea: localStorage,
        }));
        window.dispatchEvent(new StorageEvent('storage', {
          key: STORAGE_KEYS.AUTH_TOKEN, oldValue: 'old-session', newValue: 'old-session', storageArea: localStorage,
        }));
        window.dispatchEvent(new StorageEvent('storage', {
          key: STORAGE_KEYS.AUTH_TOKEN, oldValue: 'old-session', newValue: 'new-session', storageArea: sessionStorage,
        }));
      });
      expect(reloadSpy).not.toHaveBeenCalled();
      expect(localStorage.getItem(STORAGE_KEYS.CACHED_USER)).toBe(cachedUser);

      unmount();
      window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEYS.AUTH_TOKEN, oldValue: 'old-session', newValue: 'new-session', storageArea: localStorage,
      }));
      expect(reloadSpy).not.toHaveBeenCalled();
    });
  });

  it('rejects the legacy token URL and keeps the current credential while cleaning history', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    // Seed the URL with a token query param. jsdom allows this via
    // window.history.pushState.
    window.history.pushState({}, '', '/?token=from-oauth');
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(localStorage.getItem('abby_auth_token')).toBe('test-session');
    expect(result.current.sessionError).toMatch(/start again/i);
    expect(replaceState).toHaveBeenCalled();
    setToken(null);
    replaceState.mockRestore();
  });

  it('does not replace credentials or log out after unmount during Google push cleanup', async () => {
    setToken('unmount-account-a');
    await prepareGoogleCallback();
    const originalWorker = navigator.serviceWorker;
    let finish;
    const unsubscribe = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
      getRegistration: vi.fn().mockResolvedValue({ pushManager: {
        getSubscription: vi.fn().mockResolvedValue({ endpoint: 'https://push.example/unmount', unsubscribe }),
      } }),
    } });
    const logouts = [];
    server.use(
      http.post('*/api/auth/google/exchange/', () => HttpResponse.json({ mode: 'login', token: 'unmount-account-b', user: buildUser({ id: 22 }) })),
      http.post('*/api/push/unsubscribe/', () => HttpResponse.json({ ok: true, removed: 1 })),
      http.post('*/api/auth/', () => { logouts.push(true); return HttpResponse.json({ ok: true }); }),
    );
    try {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const view = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(unsubscribe).toHaveBeenCalledOnce());
      view.unmount();
      await act(async () => { finish(true); });
      await waitFor(() => expect(sessionStorage.getItem('abby_google_authorization_v1')).toBeNull());
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('unmount-account-a');
      expect(logouts).toEqual([]);
    } finally {
      Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: originalWorker });
    }
  });

  it('awaits one OAuth replacement during the real StrictMode effect replay', async () => {
    setToken('strict-account-a');
    await prepareGoogleCallback();
    const exchanges = [];
    server.use(http.post('*/api/auth/google/exchange/', ({ request }) => {
      exchanges.push(request);
      return HttpResponse.json({ mode: 'login', token: 'strict-account-b', user: buildUser({ id: 22, role: 'child' }) });
    }));
    const originalWorker = navigator.serviceWorker;
    let finish;
    const removal = new Promise((resolve) => { finish = resolve; });
    const unsubscribe = vi.fn().mockReturnValue(removal);
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
      getRegistration: vi.fn().mockResolvedValue({ pushManager: {
        getSubscription: vi.fn().mockResolvedValue({ endpoint: 'https://push.example/strict', unsubscribe }),
      } }),
    } });
    const profiles = [];
    server.use(
      http.post('*/api/push/unsubscribe/', () => HttpResponse.json({ ok: true, removed: 1 })),
      http.get('*/api/auth/me/', ({ request }) => {
        profiles.push(request.headers.get('authorization'));
        return HttpResponse.json(buildUser({ id: 22, role: 'child' }));
      }),
    );
    try {
      const wrapper = ({ children }) => <StrictMode><AuthProvider>{children}</AuthProvider></StrictMode>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(unsubscribe).toHaveBeenCalledOnce());
      expect(profiles).toEqual([]);
      await act(async () => { finish(true); });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.user?.id).toBe(22);
      expect(result.current.user?.role).toBe('child');
      expect(profiles).toEqual(['Token strict-account-b']);
      expect(exchanges).toHaveLength(1);
      expect(exchanges[0].headers.get('authorization')).toBeNull();
      expect(window.location.hash).toBe('');
      expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('strict-account-b');
    } finally {
      Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: originalWorker });
    }
  });
});

// THE-ABBY-PROJECT-3Z: boot-time GET /api/dashboard/ answered an HTML 200 on
// both client attempts while a deploy swapped containers, and every one was
// captured at once. The read now hands a persistent HTML 200 to useApi, which
// waits out the rest of the window and reports only if the proxy still fails.
describe('useApi deploy-window recovery for the dashboard read', () => {
  const html = () => new HttpResponse('<!doctype html><title>starting</title>', {
    status: 200, headers: { 'content-type': 'text/html' },
  });
  let dashboardCalls;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setToken('dashboard-session');
    dashboardCalls = 0;
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads the data without reporting when the proxy recovers after the client retry', async () => {
    server.use(http.get('*/api/dashboard/', () => {
      dashboardCalls += 1;
      return dashboardCalls <= 2 ? html() : HttpResponse.json({ week_total: 7 });
    }));
    const { result } = renderHook(() => useApi(() => apiIndex.getDashboard(), []));
    await vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS);
    expect(result.current.loading).toBe(true);
    await vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS);
    await waitFor(() => expect(result.current.data).toEqual({ week_total: 7 }));
    expect(result.current.error).toBeNull();
    expect(dashboardCalls).toBe(3);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('reports once, with both attempts counted, when the HTML persists', async () => {
    server.use(http.get('*/api/dashboard/', () => {
      dashboardCalls += 1;
      return html();
    }));
    const { result } = renderHook(() => useApi(() => apiIndex.getDashboard(), []));
    await vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS);
    expect(Sentry.captureException).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS + GATEWAY_RETRY_DELAY_MS);
    await waitFor(() => expect(result.current.error).toMatch(/temporarily unavailable/i));
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'API 200 with non-JSON body: GET /dashboard/' }),
      { extra: expect.objectContaining({ status: 200, deferredRecoveryAttempts: 2 }) },
    );
    expect(dashboardCalls).toBe(4);
  });

  it('does not wait or retry for errors that carry no deferred report', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(fn).toHaveBeenCalledTimes(1);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('stops quietly when the page unmounts during the wait', async () => {
    server.use(http.get('*/api/dashboard/', () => {
      dashboardCalls += 1;
      return html();
    }));
    const { unmount } = renderHook(() => useApi(() => apiIndex.getDashboard(), []));
    await vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS);
    unmount();
    await vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS * 2);
    expect(dashboardCalls).toBe(2);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });
});
