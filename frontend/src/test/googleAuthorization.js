import { startGoogleAuthorization } from '../auth/googleOAuth';
import { http, HttpResponse } from 'msw';
import { server } from './server';

export const GOOGLE_STATE = 'synthetic-google-state-12345678901234567890123';
export const GOOGLE_CODE = 'e'.repeat(43);
export const GOOGLE_URL = `https://accounts.google.com/o/oauth2/auth?state=synthetic&redirect_uri=${encodeURIComponent(`${window.location.origin}/api/auth/google/callback/`)}`;

export function interceptGoogleNavigation() {
  const original = window.location;
  const destinations = [];
  Object.defineProperty(window, 'location', { configurable: true,
    value: new Proxy(original, { set(target, key, value) {
      if (key === 'href') { destinations.push(value); return true; }
      return Reflect.set(target, key, value);
    } }),
  });
  return { destinations, restore: () => Object.defineProperty(window, 'location', { configurable: true, value: original }) };
}

export async function prepareGoogleCallback({ mode = 'login', forUserId, actor } = {}) {
  server.use(http.get(`*/api/auth/google/${mode === 'login' ? 'login/' : ''}`, () => HttpResponse.json({
    authorization_url: GOOGLE_URL, state: GOOGLE_STATE, expires_in: 600,
  })));
  const navigation = interceptGoogleNavigation();
  try { await startGoogleAuthorization({ mode, forUserId, actor }); } finally { navigation.restore(); }
  window.history.replaceState({}, '', `/#google_exchange=${GOOGLE_CODE}&google_state=${GOOGLE_STATE}`);
}
