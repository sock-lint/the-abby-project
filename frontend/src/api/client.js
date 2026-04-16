import * as Sentry from '@sentry/react';

const BASE = `${import.meta.env.VITE_API_URL || ''}/api`;

const TOKEN_KEY = 'abby_auth_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const token = getToken();
  const authHeader = token ? { Authorization: `Token ${token}` } : {};
  const config = {
    // Never serve API responses from the HTTP cache. If an upstream proxy
    // (Coolify / Traefik) ever returns a cacheable 200 with an HTML "app
    // is down" page for an API URL, the browser would otherwise keep
    // serving that stale HTML for hours — and res.json() would blow up on
    // `<!DOCTYPE html>`. no-store bypasses disk cache on every request.
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...authHeader, ...options.headers },
    ...options,
  };
  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }
  if (config.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  const res = await fetch(url, config);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    const errorMessage = err.error || err.detail || JSON.stringify(err);

    Sentry.addBreadcrumb({
      category: 'api',
      message: `${options.method || 'GET'} ${path} -> ${res.status}`,
      level: 'error',
      data: { status: res.status, url, response: errorMessage },
    });

    if (res.status >= 500) {
      Sentry.captureException(
        new Error(`API ${res.status}: ${options.method || 'GET'} ${path}`),
        { extra: { response: errorMessage, status: res.status } },
      );
    }

    throw new Error(errorMessage);
  }
  if (res.status === 204) return null;
  // Guard against an upstream proxy returning a 200 with an HTML error page
  // (or anything else non-JSON) — happens when the origin is down and a load
  // balancer substitutes its own body. We'd rather throw a clear error (and
  // report it to Sentry) than silently feed `<!DOCTYPE html>` into res.json().
  const contentType = res.headers?.get?.('content-type') || '';
  if (!contentType.toLowerCase().includes('application/json')) {
    const snippet = await res.text().catch(() => '');
    const preview = snippet.slice(0, 120);
    Sentry.captureException(
      new Error(`API 200 with non-JSON body: ${options.method || 'GET'} ${path}`),
      { extra: { contentType, preview, url } },
    );
    throw new Error(
      `Unexpected non-JSON response from ${path} (content-type: ${contentType || 'missing'})`,
    );
  }
  return res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, formData) => request(path, { method: 'POST', body: formData }),
};

export async function getBlob(path) {
  const url = `${BASE}${path}`;
  const token = getToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Token ${token}` } : {},
  });
  if (!res.ok) {
    const errorMessage = res.statusText || `HTTP ${res.status}`;

    Sentry.addBreadcrumb({
      category: 'api',
      message: `GET blob ${path} -> ${res.status}`,
      level: 'error',
      data: { status: res.status, url },
    });

    if (res.status >= 500) {
      Sentry.captureException(
        new Error(`Blob API ${res.status}: GET ${path}`),
        { extra: { status: res.status } },
      );
    }

    throw new Error(errorMessage);
  }
  return res.blob();
}
