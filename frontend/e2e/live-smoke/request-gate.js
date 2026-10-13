import { LIVE_BASE_URL, LiveCheckError, requireCheck, validateIdentity } from '../../scripts/live-checks-contract.mjs';

export class RequestGate {
  constructor(credentials, role) {
    this.credentials = credentials;
    this.role = role;
    this.verified = false;
    this.token = null;
    this.failures = new Set();
    this.loginDispatched = false;
    this.identityReady = new Promise((resolve) => { this.resolveIdentity = resolve; });
  }

  accept(body) {
    validateIdentity(body, this.credentials, this.role, { login: true });
    this.token = body.token;
    this.verified = true;
    this.resolveIdentity(true);
    return this.token;
  }

  cancel() { this.resolveIdentity(false); }

  inspect({ url, method, authorization, body, navigation = false }) {
    let target;
    try { target = new URL(url); } catch { return this.deny('EXTERNAL_NAVIGATION'); }
    const sameOrigin = target.origin === LIVE_BASE_URL;
    if (target.username || target.password) return this.deny('EXTERNAL_AUTH');
    if (authorization && !sameOrigin) return this.deny('EXTERNAL_AUTH');
    if (navigation && !sameOrigin) return this.deny('EXTERNAL_NAVIGATION');
    if (!sameOrigin) return ['GET', 'HEAD'].includes(method) ? 'allow' : 'abort';
    if (['GET', 'HEAD'].includes(method)) {
      if (!authorization) return 'allow';
      if (!this.verified) return 'hold';
      return authorization === `Token ${this.token}` ? 'allow' : this.deny('IDENTITY');
    }
    const actor = this.credentials[this.role];
    if (method === 'POST' && target.pathname === '/api/auth/' && !authorization
      && body?.action === 'login' && body.username === actor.username && body.password === actor.password
      && !this.verified && !this.loginDispatched) {
      this.loginDispatched = true;
      return 'allow';
    }
    return this.deny('UNEXPECTED_MUTATION');
  }

  deny(code) {
    this.failures.add(code);
    return 'abort';
  }

  assertSafe() {
    requireCheck(this.failures.size === 0, [...this.failures][0]);
  }

  observeResponse(url, status) {
    const target = new URL(url);
    if (target.origin === LIVE_BASE_URL && target.pathname.startsWith('/api/') && status >= 500) {
      this.failures.add('BROWSER');
    }
  }
}

export function installRedirectFence() {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, options) => {
    const request = new Request(input, options);
    if (request.headers.has('Authorization')
      || (new URL(request.url).pathname === '/api/auth/' && request.method === 'POST')) {
      return nativeFetch(new Request(request, { redirect: 'error' }));
    }
    return nativeFetch(input, options);
  };
}

export async function installRequestGate(context, gate) {
  // Continue/abort preserve the deployed response. Playwright routes do not
  // intercept every redirect hop, so native fetch must refuse credentialed
  // redirects before a password body or token can reach a different target.
  await context.addInitScript(installRedirectFence);
  context.on('response', (response) => gate.observeResponse(response.url(), response.status()));
  context.on('weberror', () => { gate.failures.add('BROWSER'); });
  await context.route('**/*', async (route) => {
    const request = route.request();
    let body;
    if (request.method() === 'POST') {
      try { body = request.postDataJSON(); } catch { /* Invalid bodies cannot match the login allowance. */ }
    }
    const properties = {
      url: request.url(), method: request.method(),
      authorization: request.headers().authorization,
      body, navigation: request.isNavigationRequest(),
    };
    let decision = gate.inspect(properties);
    if (decision === 'hold') {
      const accepted = await gate.identityReady;
      decision = accepted ? gate.inspect(properties) : 'abort';
    }
    try {
      if (decision === 'allow') await route.continue();
      else await route.abort('blockedbyclient');
    } catch (error) {
      if (error instanceof LiveCheckError) throw error;
      // Closing the fresh context during cleanup can cancel an in-flight route.
    }
  });
}
