import * as Sentry from '@sentry/react';

import { STORAGE_KEYS } from '../constants/storage';
import { purgePrivateApiCaches } from '../pwa/privacy';
import { apiUrl } from './urls';
import { summarizeResponse } from './responseDiagnostics';

export const AUTH_CHANGED_EVENT = 'abby:auth-changed';
let readToken;
let readNamespace;

// A prompted worker upgrade leaves the old worker controlling this page.
// Fresh noncredential query keys prevent it matching another session's JSON,
// including an old request which completes after its cache was purged.
function privateReadUrl(path, token) {
  if (readToken !== token || !readNamespace) {
    readToken = token;
    readNamespace = crypto.randomUUID();
  }
  const url = new URL(apiUrl(path), window.location.origin);
  url.searchParams.set('_abby_session', readNamespace);
  return url.href;
}

export function getToken() {
  return localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN) || '';
}

export function setToken(token) {
  const previous = getToken();
  if (previous !== (token || '')) {
    localStorage.removeItem(STORAGE_KEYS.CACHED_USER);
    readNamespace = undefined;
    void purgePrivateApiCaches();
  }
  if (token) {
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, token);
  } else {
    localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
  }
  if (previous !== (token || '')) window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

// Requests can finish after another tab/client has logged out or switched
// accounts. Only remove the credential that the completed request used.
export function clearTokenIfCurrent(token) {
  if (getToken() !== token) return false;
  setToken(null);
  return true;
}

// Audit L5: coalesce concurrent 401-triggered reloads. If a page issues
// multiple parallel API calls and the stored token is stale, every
// failing call hits the self-heal path and would queue its own
// ``window.location.reload()``. Browsers usually merge these but not
// always; the flag guarantees only the first 401 reloads. Reset on
// module load (i.e. after the reload completes) is automatic.
let _reloadInFlight = false;
function _selfHealReload(token) {
  if (_reloadInFlight || !token || !clearTokenIfCurrent(token)) return;
  _reloadInFlight = true;
  window.location.reload();
}

// Test-only escape hatch: in real-page lifetime the flag resets via the
// reload itself, but in tests the reload is mocked so the flag would
// otherwise leak between cases. Tests call this in ``beforeEach``.
export function __resetSelfHealForTesting() {
  _reloadInFlight = false;
}

// A dead connection rejects `fetch` with the browser's own wording — "Failed
// to fetch" on Chrome, "Load failed" on Safari — and ~79 call sites render
// `err.message` straight into an ErrorAlert. Translating here rather than at
// each call site covers every one of them, and keeps the shape callers expect:
// no `.status` (it never reached the server), so the 401 self-heal and every
// `err.status === 409` branch are unaffected.
export const OFFLINE_MESSAGE = 'No connection — check your wifi and try again.';
const UNAVAILABLE_MESSAGE = 'Abby is temporarily unavailable. Please try again in a moment.';

function asOfflineError(cause) {
  const err = new Error(OFFLINE_MESSAGE);
  err.offline = true;
  err.cause = cause;
  return err;
}

// AbortError is a caller-initiated cancel (useApi aborts in-flight requests on
// unmount and on dep changes), not a connection failure — it must pass through
// untouched or those aborts start rendering as "no connection".
async function fetchOrOffline(url, config) {
  try {
    return await fetch(url, config);
  } catch (err) {
    if (err?.name === 'AbortError') throw err;
    throw asOfflineError(err);
  }
}

async function request(path, options = {}) {
  const { token: explicitToken, selfHeal = true, ...fetchOptions } = options;
  const token = explicitToken ?? getToken();
  const method = (fetchOptions.method || 'GET').toUpperCase();
  let url = method === 'GET'
    ? privateReadUrl(path, token) : apiUrl(path);
  const authHeader = token ? { Authorization: `Token ${token}` } : {};
  const config = {
    // Never serve API responses from the HTTP cache. If an upstream proxy
    // (Coolify / Traefik) ever returns a cacheable 200 with an HTML "app
    // is down" page for an API URL, the browser would otherwise keep
    // serving that stale HTML for hours — and res.json() would blow up on
    // `<!DOCTYPE html>`. no-store bypasses disk cache on every request.
    cache: 'no-store',
    ...fetchOptions,
    headers: { 'Content-Type': 'application/json', ...authHeader, ...fetchOptions.headers },
  };
  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }
  if (config.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  const hadAuth = Boolean(config.headers?.Authorization);
  let res = await fetchOrOffline(url, config);
  let attempts = 1;
  // A deployment proxy can return a cacheable HTML error page with a success
  // status. Retry reads once at a fresh URL, since no-store alone cannot evict
  // a response already cached upstream. Never replay a possible write.
  while (res.ok && res.status !== 204) {
    const contentType = res.headers?.get?.('content-type') || '';
    if (contentType.toLowerCase().includes('application/json')) break;
    const preview = (await res.text().catch(() => '')).slice(0, 120);
    config.signal?.throwIfAborted();
    if (method === 'GET' && attempts === 1 && getToken() === token) {
      Sentry.addBreadcrumb({
        category: 'api',
        message: `Retrying ${method} ${path} after a non-JSON response`,
        level: 'warning',
        data: { status: res.status, contentType, responseDiagnostics: summarizeResponse(res, url) },
      });
      const retryUrl = new URL(url, window.location.origin);
      retryUrl.searchParams.set('_abby_retry', crypto.randomUUID());
      url = retryUrl.href;
      attempts += 1;
      res = await fetchOrOffline(url, config);
      continue;
    }
    Sentry.captureException(
      new Error(`API ${res.status} with non-JSON body: ${method} ${path}`),
      { extra: { contentType, preview, url, status: res.status, attempts, responseDiagnostics: summarizeResponse(res, url) } },
    );
    throw new Error(UNAVAILABLE_MESSAGE);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    const errorMessage = err.error || err.detail || JSON.stringify(err);

    Sentry.addBreadcrumb({
      category: 'api',
      message: `${options.method || 'GET'} ${path} -> ${res.status}`,
      level: 'error',
      data: { status: res.status, url, response: errorMessage },
    });

    // Self-heal on a stale token: if we sent an Authorization header and
    // the server rejected it, the stored token is no longer valid (the
    // token row went away during a redeploy, got rotated, etc). Clear it
    // and reload so AuthProvider's boot flow lands on the Login page
    // without requiring users to manually purge browser session data.
    // Skipped when no auth header was sent — that path is legitimate
    // anonymous access (boot-time getMe, login-form credential retries).
    // Only clear the credential this request used: a delayed 401 must not
    // discard a newer sign-in. Concurrent 401s coalesce — see audit L5.
    if (res.status === 401 && hadAuth && selfHeal) {
      _selfHealReload(token);
    }

    if (res.status >= 500) {
      Sentry.captureException(
        new Error(`API ${res.status}: ${options.method || 'GET'} ${path}`),
        { extra: { response: errorMessage, status: res.status } },
      );
    }

    // Attach status + parsed body so callers can branch on specific codes
    // (e.g., the Journal modal treats 409 as "already wrote today, switch
    // to edit mode" using `err.response.existing`). The default human
    // message stays on .message so untyped `catch` blocks still work.
    const apiError = new Error(errorMessage);
    apiError.status = res.status;
    apiError.response = err;
    throw apiError;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path, options) => request(path, options),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, formData) => request(path, { method: 'POST', body: formData }),
};

export async function getBlob(path) {
  const token = getToken();
  const url = privateReadUrl(path, token);
  const hadAuth = Boolean(token);
  const res = await fetchOrOffline(url, {
    cache: 'no-store',
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

    // Same self-heal path as `request()` — see that function's comment.
    if (res.status === 401 && hadAuth) {
      _selfHealReload(token);
    }

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
