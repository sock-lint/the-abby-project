const RESPONSE_TYPES = new Set(['basic', 'cors', 'default', 'error', 'opaque', 'opaqueredirect']);

function httpUrl(value, base) {
  if (typeof value !== 'string' || !value) return null;
  if (base && !/^https?:\/\//i.test(value) && (!value.startsWith('/') || value.startsWith('//'))) return null;
  try {
    const url = new URL(value, base);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return url;
  } catch {
    return null;
  }
}

function serviceWorkerControlled() {
  try {
    const worker = globalThis.navigator?.serviceWorker;
    return worker && 'controller' in worker ? Boolean(worker.controller) : null;
  } catch {
    return null;
  }
}

// Report relationships, never the final URL, headers, body, or worker identity.
// Worker control and redirect metadata are clues; neither proves an HTML source.
export function summarizeResponse(response, requestedUrl) {
  const summary = {
    redirected: null,
    originRelation: 'unknown',
    pathRelation: 'unknown',
    responseType: 'unknown',
    serviceWorkerControlled: serviceWorkerControlled(),
  };
  try {
    const redirected = response?.redirected;
    const responseType = response?.type;
    if (typeof redirected === 'boolean') summary.redirected = redirected;
    if (RESPONSE_TYPES.has(responseType)) summary.responseType = responseType;
    // Native Response.url is absolute. Only the requested URL may be relative.
    const finalUrl = httpUrl(response?.url);
    const requestUrl = httpUrl(requestedUrl, globalThis.location?.origin);
    if (finalUrl && requestUrl) {
      summary.originRelation = finalUrl.origin === requestUrl.origin ? 'same_origin' : 'cross_origin';
      summary.pathRelation = finalUrl.pathname === requestUrl.pathname
        ? 'same_path'
        : /^\/api(?:\/|$)/.test(finalUrl.pathname) ? 'other_api_path' : 'other_path';
    }
  } catch {
    // Diagnostics must not replace the original malformed-response error.
  }
  return summary;
}
