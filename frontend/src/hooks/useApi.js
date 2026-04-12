import { useState, useEffect, useCallback } from 'react';
import { getMe, login as apiLogin, logout as apiLogout } from '../api';
import { setToken } from '../api/client';

export function useApi(apiFn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
  }, deps);

  useEffect(() => { load(); }, [load]);

  return { data, loading, error, reload: load, setData };
}

export function useAuth() {
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

    getMe().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }, []);

  const doLogin = async (username, password) => {
    const u = await apiLogin(username, password);
    setUser(u);
    return u;
  };

  const doLogout = async () => {
    await apiLogout();
    setUser(null);
  };

  return { user, loading, login: doLogin, logout: doLogout };
}
