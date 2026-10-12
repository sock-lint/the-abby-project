import { isNativeRuntime } from '../platform/runtime';

export function apiUrl(path) {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('API paths must be relative to the configured backend.');
  }
  const configured = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
  if (!configured) {
    if (isNativeRuntime()) throw new Error('The native prototype requires a configured HTTPS API origin.');
    return `/api${path}`;
  }
  let origin;
  try { origin = new URL(configured); } catch { throw new Error('Invalid API origin.'); }
  if (!['https:', 'http:'].includes(origin.protocol)
    || origin.username || origin.password || origin.search || origin.hash
    || origin.pathname !== '/') {
    throw new Error('Invalid API origin.');
  }
  if (isNativeRuntime() && origin.protocol !== 'https:') {
    throw new Error('The native prototype requires a configured HTTPS API origin.');
  }
  return `${origin.origin}/api${path}`;
}

// Local Django sprite storage emits /media/... URLs. A packaged WebView's
// origin owns the app bundle, so these public assets need the API origin.
export function backendMediaUrl(value) {
  if (!value || !isNativeRuntime()) return value;
  try {
    const url = new URL(value, apiUrl('/'));
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}
