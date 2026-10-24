import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import {
  getGoogleConfig, getGoogleLoginUrl, getGoogleAuthUrl, exchangeGoogleAuthorization,
} from './index';
import config from '../../../contracts/api/fixtures/google-auth-config.json';
import init from '../../../contracts/api/fixtures/google-auth-init.json';
import login from '../../../contracts/api/fixtures/google-auth-login.json';
import linked from '../../../contracts/api/fixtures/google-auth-linked.json';
import busy from '../../../contracts/api/fixtures/google-auth-busy.json';
import { getToken } from './client';

describe('Google authorization API contracts', () => {
  it('preserves a busy authorization code and current session without automatically retrying', async () => {
    const token = getToken();
    const requests = [];
    server.use(http.get('*/api/auth/google/login/', ({ request }) => {
      requests.push(request);
      return HttpResponse.json(busy, { status: 503 });
    }));
    await expect(getGoogleLoginUrl('c'.repeat(43))).rejects.toMatchObject({
      status: 503, message: busy.error, response: { code: 'authorization_busy', error: busy.error },
    });
    expect(requests).toHaveLength(1);
    expect(requests[0].headers.get('authorization')).toBeNull();
    expect(getToken()).toBe(token);
  });

  it('reads availability without attaching an existing session or creating an authorization', async () => {
    const requests = [];
    server.use(http.get('*/api/auth/google/config/', ({ request }) => {
      requests.push(request);
      return HttpResponse.json(config);
    }));
    expect(await getGoogleConfig()).toEqual({ configured: true });
    expect(requests).toHaveLength(1);
    expect(requests[0].headers.get('authorization')).toBeNull();
    expect(new URL(requests[0].url).searchParams.has('code_challenge')).toBe(false);
  });

  it.each(['login', 'link'])('reads the %s init fixture with an S256 challenge and preserved target/auth scope', async (mode) => {
    const requests = [];
    const challenge = 'c'.repeat(43);
    server.use(http.get(`*/api/auth/google/${mode === 'login' ? 'login/' : ''}`, ({ request }) => {
      requests.push(request);
      return HttpResponse.json(init);
    }));
    const response = mode === 'login'
      ? await getGoogleLoginUrl(challenge)
      : await getGoogleAuthUrl(7, challenge, { token: 'captured-parent', selfHeal: false });
    expect(response).toEqual(init);
    expect(response.state).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(response.expires_in).toBe(600);
    const url = new URL(requests[0].url);
    expect(url.searchParams.get('code_challenge')).toBe(challenge);
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(url.searchParams.get('for_user')).toBe(mode === 'link' ? '7' : null);
    expect(requests[0].headers.get('authorization')).toBe(mode === 'link' ? 'Token captured-parent' : null);
    expect(response).not.toHaveProperty('token');
    expect(new URL(response.authorization_url).searchParams.has('token')).toBe(false);
  });

  it.each([login, linked])('reads the $mode receipt with the verifier only in the POST body', async (receipt) => {
    const requests = [];
    const body = { exchange_code: 'e'.repeat(43), code_verifier: 'v'.repeat(43) };
    server.use(http.post('*/api/auth/google/exchange/', async ({ request }) => {
      requests.push({ request, body: await request.json() });
      return HttpResponse.json(receipt);
    }));
    expect(await exchangeGoogleAuthorization(body, {
      token: receipt.mode === 'link' ? 'captured-parent' : '', selfHeal: false,
    })).toEqual(receipt);
    expect(requests).toHaveLength(1);
    expect(requests[0].body).toEqual(body);
    expect(requests[0].request.url).not.toContain(body.exchange_code);
    expect(requests[0].request.url).not.toContain(body.code_verifier);
    expect(requests[0].request.headers.get('authorization')).toBe(receipt.mode === 'link' ? 'Token captured-parent' : null);
    if (receipt.mode === 'login') {
      expect(receipt.token).toMatch(/^[a-f0-9]{40}$/);
      expect(receipt.user.family.id).toBe(901);
      expect(receipt.user.google_linked).toBe(true);
      expect(receipt.user.usage_collection_enabled).toBe(true);
    } else expect(receipt).toEqual({ mode: 'link', linked: true });
  });
});
