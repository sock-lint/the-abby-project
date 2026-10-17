import { getGoogleAuthUrl, getGoogleLoginUrl, exchangeGoogleAuthorization } from '../api';
import { getToken } from '../api/client';
import { apiUrl } from '../api/urls';
import { isNativeRuntime } from '../platform/runtime';
import { replaceSessionToken } from '../pwa/pushSession';
import { STORAGE_KEYS } from '../constants/storage';

const STORAGE_KEY = 'abby_google_authorization_v1';
const MAX_AGE = 600_000;
const HOSTED_ONLY = 'Google authorization is available in Abby’s hosted browser app. Open it there to connect your account.';
const RESTART = 'Google sign-in could not be completed. Start again from Abby.';
const INTERRUPTED = 'Google sign-in was interrupted. Start again from Abby.';
const ERRORS = {
  access_denied: 'Google authorization was cancelled. Your Abby account has not changed.',
  cancelled: 'Google authorization was cancelled. Your Abby account has not changed.',
  denied: 'Google authorization was cancelled or denied. Your Abby account has not changed.',
  no_account: 'No linked Google account found. Link your Google account in Settings first.',
  inactive: 'Your account is inactive.',
  already_linked_other: 'That Google account is already linked to another Abby account.',
  authorization_changed: 'Your Abby account or family changed. Start Google authorization again.',
};
let capturedCallback = null;
let redemption = null;
let linkResult = null;

function readAttempt() {
  try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null'); } catch { return null; }
}

function saveAttempt(attempt) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(attempt));
    if (readAttempt()?.id !== attempt.id) throw new Error();
  } catch {
    throw new Error('Google authorization needs browser session storage. Allow it for Abby and try again.');
  }
}

function removeAttempt(id) {
  if (readAttempt()?.id === id) {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* Expiry still bounds unreadable state. */ }
  }
}

function backendScope() {
  return new URL(apiUrl('/'), window.location.origin).href;
}

export function supportsGoogleReturn() {
  try {
    return !isNativeRuntime() && new URL(backendScope()).origin === window.location.origin;
  } catch { return false; }
}

function base64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

async function hash(value) {
  if (!crypto.subtle) throw new Error('Google authorization needs a secure browser connection. Open Abby with HTTPS.');
  return base64url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))));
}

function validAttempt(attempt) {
  return attempt?.version === 1 && attempt.origin === window.location.origin
    && attempt.backend === backendScope() && attempt.expiresAt > Date.now()
    && attempt.expiresAt <= Date.now() + MAX_AGE && ['login', 'link'].includes(attempt.mode)
    && /^[A-Za-z0-9_-]{43}$/.test(attempt.verifier)
    && typeof attempt.fingerprint === 'string';
}

async function currentAttempt(attempt, token) {
  const fingerprint = await hash(token);
  return getToken() === token && validAttempt(attempt)
    && readAttempt()?.id === attempt.id && fingerprint === attempt.fingerprint;
}

// Starts run only after an explicit click. The verifier never enters a URL or
// localStorage; only its S256 challenge leaves the initiating browser tab.
export async function startGoogleAuthorization({ mode, forUserId, actor, isCurrent = () => true }) {
  if (!supportsGoogleReturn()) {
    throw new Error(HOSTED_ONLY);
  }
  const token = getToken();
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const [challenge, fingerprint] = await Promise.all([hash(verifier), hash(token)]);
  if (getToken() !== token || !isCurrent()) return false;
  const attempt = {
    version: 1, id: crypto.randomUUID(), mode, verifier, fingerprint,
    origin: window.location.origin, backend: backendScope(),
    actorId: actor?.id ?? null, familyId: actor?.family?.id ?? null, targetId: forUserId ?? null,
    expiresAt: Date.now() + MAX_AGE, phase: 'starting',
  };
  saveAttempt(attempt);
  try {
    const options = { token: mode === 'link' ? token : '', selfHeal: false };
    const response = mode === 'link'
      ? await getGoogleAuthUrl(forUserId, challenge, options)
      : await getGoogleLoginUrl(challenge, options);
    if (!await currentAttempt(attempt, token) || !isCurrent()) {
      removeAttempt(attempt.id);
      return false;
    }
    const url = new URL(response.authorization_url);
    const callbackUrl = new URL(url.searchParams.get('redirect_uri'));
    if (callbackUrl.origin !== window.location.origin) throw new Error(HOSTED_ONLY);
    if (url.protocol !== 'https:' || url.hostname !== 'accounts.google.com'
      || url.username || url.password || !/^[A-Za-z0-9_-]{20,128}$/.test(response.state)
      || callbackUrl.origin !== window.location.origin || callbackUrl.pathname !== '/api/auth/google/callback/'
      || callbackUrl.username || callbackUrl.password || callbackUrl.search || callbackUrl.hash
      || !Number.isFinite(response.expires_in) || response.expires_in <= 0) throw new Error(RESTART);
    saveAttempt({ ...attempt, state: response.state, phase: 'awaiting',
      expiresAt: Date.now() + Math.min(response.expires_in * 1000, MAX_AGE) });
    window.location.href = url.href;
    return true;
  } catch (error) {
    removeAttempt(attempt.id);
    throw error;
  }
}

export function cancelGoogleAuthorization() {
  const attempt = readAttempt();
  if (attempt) removeAttempt(attempt.id);
}

// Called synchronously before Sentry.init and before any async auth work.
// Fragments are not sent to the server; replaceState also keeps them out of
// telemetry, copied links and the visible history entry.
export function captureGoogleCallback() {
  const query = new URLSearchParams(window.location.search);
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const retired = /^\/play(?:\/|$)/.test(window.location.pathname);
  const legacyToken = query.has('token');
  const hasCallback = fragment.has('google_exchange') || fragment.has('google_error') || fragment.has('google_state');
  if (retired && (window.location.search || window.location.hash) || legacyToken || hasCallback) {
    window.history.replaceState({}, '', window.location.pathname);
  }
  if (retired) return;
  if (legacyToken) {
    capturedCallback = { error: RESTART };
    return;
  }
  if (!hasCallback) return;
  const attempt = readAttempt();
  if (!supportsGoogleReturn() || !validAttempt(attempt) || !attempt.state
    || attempt.state !== fragment.get('google_state') || attempt.phase !== 'awaiting') {
    capturedCallback = { error: RESTART };
    return;
  }
  const code = fragment.get('google_exchange');
  const providerError = fragment.get('google_error');
  if (providerError) {
    capturedCallback = { attempt, error: ERRORS[providerError] || RESTART };
    removeAttempt(attempt.id);
    return;
  }
  if (!/^[A-Za-z0-9_-]{43}$/.test(code || '')) {
    capturedCallback = { error: RESTART };
    removeAttempt(attempt.id);
    return;
  }
  try {
    saveAttempt({ ...attempt, exchangeCode: code, phase: 'returned' });
  } catch (error) {
    capturedCallback = { error: error.message };
  }
}

function finishLink(attempt, token, error = '') {
  if (attempt?.mode !== 'link' || getToken() !== token) return;
  linkResult = { token, error };
  window.history.replaceState({}, '', '/settings');
}

export function takeGoogleLinkResult() {
  const result = linkResult;
  linkResult = null;
  return result && result.token === getToken() ? result : null;
}

// A real navigation creates a fresh module. Tests use this to model a new
// document while deliberately preserving sessionStorage for reload cases.
export function __resetGoogleAuthorizationForTesting() {
  capturedCallback = null;
  redemption = null;
  linkResult = null;
}

// An in-memory promise survives React StrictMode's effect replay. A new page
// finding `exchanging` cannot know whether the POST committed, so it must not
// resend a single-use exchange. Restarting is safe and leaves the old session.
export function completeGoogleAuthorization({ isCurrent = () => true } = {}) {
  captureGoogleCallback();
  if (redemption) return redemption;
  const callback = capturedCallback;
  capturedCallback = null;
  const attempt = callback?.attempt || readAttempt();
  if (!callback && !['returned', 'exchanging'].includes(attempt?.phase)) return Promise.resolve(null);
  const token = getToken();
  redemption = (async () => {
    if (callback?.error) {
      if (!isCurrent() || callback.attempt && readAttempt() && readAttempt().id !== callback.attempt.id) return null;
      if (callback.attempt && getToken() === token
        && await hash(token) === callback.attempt.fingerprint) finishLink(callback.attempt, token, callback.error);
      return { error: callback.error };
    }
    if (!await currentAttempt(attempt, token)) {
      removeAttempt(attempt?.id);
      return { error: RESTART };
    }
    if (!isCurrent()) { removeAttempt(attempt.id); return null; }
    if (attempt.phase === 'exchanging') {
      removeAttempt(attempt.id);
      finishLink(attempt, token, INTERRUPTED);
      return { error: INTERRUPTED };
    }
    try {
      saveAttempt({ ...attempt, phase: 'exchanging' });
      const result = await exchangeGoogleAuthorization({ exchange_code: attempt.exchangeCode, code_verifier: attempt.verifier },
        { token: attempt.mode === 'link' ? token : '', selfHeal: false });
      if (!await currentAttempt(attempt, token) || !isCurrent()) return null;
      if (result.mode !== attempt.mode || result.mode === 'login' && (!result.token || !result.user)
        || result.mode === 'link' && result.linked !== true) throw new Error(RESTART);
      if (result.mode === 'login') {
        // This final synchronous fence matters: the replacement helper must
        // never capture and sign out an account newer than this attempt.
        if (getToken() !== token || readAttempt()?.id !== attempt.id) return null;
        localStorage.removeItem(STORAGE_KEYS.CACHED_USER);
        await replaceSessionToken(result.token, {
          expectedToken: token, isCurrent: () => isCurrent() && readAttempt()?.id === attempt.id,
        });
      } else finishLink(attempt, token);
      return result;
    } catch (error) {
      if (getToken() !== token || readAttempt()?.id !== attempt.id || !isCurrent()) return null;
      const message = ERRORS[error.response?.code] || (error.message?.includes('notifications') ? error.message : INTERRUPTED);
      finishLink(attempt, token, message);
      return { error: message, stopBoot: message.includes('notifications') };
    } finally {
      removeAttempt(attempt.id);
    }
  })().catch(() => ({ error: RESTART }));
  return redemption;
}
