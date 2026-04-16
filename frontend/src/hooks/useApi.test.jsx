import { act, renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';
import * as apiIndex from '../api/index.js';
import { setToken } from '../api/client.js';
import { AuthProvider, useApi, useAuth } from './useApi.js';

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
    await act(async () => { await result.current.reload(); });
    expect(result.current.data).toEqual({ n: 2 });
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('setData mutates locally without re-fetching', async () => {
    const fn = vi.fn().mockResolvedValue(1);
    const { result } = renderHook(() => useApi(fn, []));
    await waitFor(() => expect(result.current.data).toBe(1));
    act(() => result.current.setData(99));
    expect(result.current.data).toBe(99);
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
    expect(result.current.loading).toBe(false);
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

    it('logout() clears user', async () => {
      server.use(
        http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      );
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.user).not.toBeNull());
      await act(async () => { await result.current.logout(); });
      expect(result.current.user).toBeNull();
      expect(logoutSpy).toHaveBeenCalled();
    });
  });

  it('consumes ?token= from the URL and cleans history', async () => {
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
    expect(localStorage.getItem('abby_auth_token')).toBe('from-oauth');
    expect(replaceState).toHaveBeenCalled();
    setToken(null);
    replaceState.mockRestore();
  });
});
