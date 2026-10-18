import { afterEach, describe, expect, it, vi } from 'vitest';
import { summarizeResponse } from './responseDiagnostics';

const requested = 'https://abby.example/api/pulse/?_abby_session=synthetic';
const response = (url, overrides = {}) => ({ url, redirected: false, type: 'basic', ...overrides });
const expectedKeys = ['originRelation', 'pathRelation', 'redirected', 'responseType', 'serviceWorkerControlled'];

afterEach(() => vi.unstubAllGlobals());

describe('malformed-response diagnostic summary', () => {
  it.each([
    [requested, 'same_origin', 'same_path'],
    ['https://abby.example/api/children/123?token=private-value#secret', 'same_origin', 'other_api_path'],
    ['https://abby.example/api', 'same_origin', 'other_api_path'],
    ['https://abby.example/private/person@example.invalid?password=secret', 'same_origin', 'other_path'],
    ['https://other.example/api/pulse/?token=private-value', 'cross_origin', 'same_path'],
    ['https://other.example/api/children/123', 'cross_origin', 'other_api_path'],
    ['https://other.example/login?token=private-value', 'cross_origin', 'other_path'],
  ])('classifies final URL relationships without exporting values: %s', (url, originRelation, pathRelation) => {
    const summary = summarizeResponse(response(url, { redirected: true }), requested);
    expect(summary).toEqual({ redirected: true, originRelation, pathRelation, responseType: 'basic', serviceWorkerControlled: false });
    expect(Object.keys(summary).sort()).toEqual(expectedKeys);
    expect(JSON.stringify(summary)).not.toMatch(/abby\.example|other\.example|123|private-value|password|secret|@/);
  });

  it('compares against the configured request origin rather than the shell origin', () => {
    expect(summarizeResponse(response('https://staging.example/api/pulse/'), 'https://staging.example/api/pulse/'))
      .toMatchObject({ originRelation: 'same_origin', pathRelation: 'same_path' });
    expect(summarizeResponse(response(`${window.location.origin}/api/pulse/`), '/api/pulse/'))
      .toMatchObject({ originRelation: 'same_origin', pathRelation: 'same_path' });
  });

  it.each([
    '', undefined, null, 7, {}, '/api/pulse/', 'not a URL',
    'https://[invalid', 'javascript:secret', 'data:text/html,secret', 'file:///private/secret',
    'https://user:secret@abby.example/api/pulse/',
  ])('keeps invalid or unavailable final URL relationships unknown: %s', (url) => {
    const summary = summarizeResponse(response(url), requested);
    expect(summary).toMatchObject({ originRelation: 'unknown', pathRelation: 'unknown' });
    expect(Object.keys(summary).sort()).toEqual(expectedKeys);
    expect(JSON.stringify(summary)).not.toMatch(/secret|private|invalid/);
  });

  it.each([undefined, null, 'not a URL', '//private.example/secret', 'data:text/html,secret', { token: 'secret' }])('keeps relationships unknown without a valid request URL: %s', (url) => {
    expect(summarizeResponse(response(requested), url)).toMatchObject({ originRelation: 'unknown', pathRelation: 'unknown' });
  });

  it.each(['basic', 'cors', 'default', 'error', 'opaque', 'opaqueredirect'])('allowlists native response type %s', (type) => {
    expect(summarizeResponse(response(requested, { type }), requested).responseType).toBe(type);
  });

  it.each([undefined, null, {}, 'secret-token', 'BASIC'])('does not export an unrecognized response type: %s', (type) => {
    expect(summarizeResponse(response(requested, { type, redirected: 'secret-token' }), requested))
      .toMatchObject({ responseType: 'unknown', redirected: null });
  });

  it('reads no response body or headers', () => {
    const metadata = response(requested);
    Object.defineProperties(metadata, {
      headers: { get() { throw new Error('Do not inspect headers'); } },
      body: { get() { throw new Error('Do not inspect body'); } },
    });
    expect(summarizeResponse(metadata, requested)).toMatchObject({ originRelation: 'same_origin', responseType: 'basic' });
  });

  it('uses each allowlisted metadata value once even if getters change', () => {
    let redirects = 0;
    let types = 0;
    expect(summarizeResponse({
      url: requested,
      get redirected() { return redirects++ === 0 ? true : 'secret-token'; },
      get type() { return types++ === 0 ? 'basic' : 'secret-token'; },
    }, requested)).toMatchObject({ redirected: true, responseType: 'basic' });
    expect(redirects).toBe(1);
    expect(types).toBe(1);
  });

  it('records only whether a service worker controls the page', () => {
    vi.stubGlobal('navigator', { serviceWorker: { controller: { scriptURL: 'https://private.example/secret-worker.js' } } });
    const summary = summarizeResponse(response(requested), requested);
    expect(summary.serviceWorkerControlled).toBe(true);
    expect(JSON.stringify(summary)).not.toMatch(/private|secret|worker\.js/);
  });

  it.each([undefined, {}, { serviceWorker: {} }])('handles unavailable service-worker metadata: %s', (navigator) => {
    vi.stubGlobal('navigator', navigator);
    expect(summarizeResponse(response(requested), requested).serviceWorkerControlled).toBeNull();
  });

  it('keeps restricted browser metadata unknown without throwing', () => {
    vi.stubGlobal('navigator', { get serviceWorker() { throw new Error('Access denied'); } });
    const summary = summarizeResponse({ get url() { throw new Error('Unavailable'); } }, requested);
    expect(summary).toEqual({ redirected: null, originRelation: 'unknown', pathRelation: 'unknown', responseType: 'unknown', serviceWorkerControlled: null });
  });
});
