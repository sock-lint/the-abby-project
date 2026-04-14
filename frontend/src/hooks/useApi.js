import * as Sentry from '@sentry/react';
import {
  createContext, createElement, useCallback, useContext, useEffect, useState,
} from 'react';
import { getMe, login as apiLogin, logout as apiLogout } from '../api';
import { setToken } from '../api/client';

export function useApi(apiFn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ``deps`` is dynamic — callers pass an array literal that changes per
  // call site, so this hook intentionally trusts them rather than statically
  // verifying. ``apiFn`` is captured by closure on each render and re-bound
  // when ``deps`` changes; including it would re-fetch on every render.
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFn();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { load(); }, [load]);

  return { data, loading, error, reload: load, setData };
}

// --- Auth context ----------------------------------------------------------
// Single source of truth for the logged-in user. Wrap the app in
// <AuthProvider> and every useAuth() / useRole() call reads the same state,
// so logout propagates globally and /api/users/me is fetched once per session.

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Handle token from Google OAuth callback redirect
    const params = new URLSearchParams(window.location.search);
    const oauthToken = params.get('token');
    if (oauthToken) {
      setToken(oauthToken);
      // Clean the URL so the token isn't visible / bookmarkable
      window.history.replaceState({}, '', window.location.pathname);
    }

    getMe()
      .then((u) => {
        setUser(u);
        Sentry.setUser(u ? { id: u.id, username: u.username, role: u.role } : null);
      })
      .catch(() => {
        setUser(null);
        Sentry.setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username, password) => {
    const u = await apiLogin(username, password);
    setUser(u);
    Sentry.setUser(u ? { id: u.id, username: u.username, role: u.role } : null);
    return u;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    Sentry.setUser(null);
  }, []);

  const value = { user, loading, login, logout };
  return createElement(AuthContext.Provider, { value }, children);
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
