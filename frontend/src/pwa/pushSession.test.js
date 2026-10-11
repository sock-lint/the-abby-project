import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { logout, login } from '../api';
import { getToken, setToken } from '../api/client';
import { bindPushSession, disconnectPushSession, replaceSessionToken, rememberPushBinding } from './pushSession';

const originalWorker = navigator.serviceWorker;
afterEach(() => Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: originalWorker }));

function installSubscription() {
  const subscription = {
    endpoint: 'https://push.example/current', unsubscribe: vi.fn().mockResolvedValue(true),
    toJSON: () => ({ endpoint: 'https://push.example/current', keys: { p256dh: 'p', auth: 'a' } }),
  };
  const registration = { pushManager: { getSubscription: vi.fn().mockResolvedValue(subscription) } };
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
    getRegistration: vi.fn().mockResolvedValue(registration),
  } });
  return { subscription, registration };
}

describe('push account teardown', () => {
  it('offline logout stops the browser subscription and clears the session', async () => {
    setToken('account-a');
    const { subscription } = installSubscription();
    server.use(
      http.post('*/api/auth/', () => HttpResponse.error()),
      http.post('*/api/push/unsubscribe/', ({ request }) => {
        expect(subscription.unsubscribe).toHaveBeenCalledOnce();
        expect(request.headers.get('authorization')).toBe('Token account-a');
        return HttpResponse.error();
      }),
    );
    await expect(logout()).rejects.toThrow(/connection/i);
    expect(subscription.unsubscribe).toHaveBeenCalledOnce();
    expect(getToken()).toBe('');
  });

  it('login stops the previous account endpoint before installing its replacement credential', async () => {
    setToken('account-a');
    const { subscription } = installSubscription();
    const requests = [];
    server.use(
      http.post('*/api/auth/', () => HttpResponse.json({ token: 'account-b' })),
      http.post('*/api/push/unsubscribe/', async ({ request }) => {
        requests.push({ auth: request.headers.get('authorization'), body: await request.json() });
        expect(getToken()).toBe('account-a');
        expect(subscription.unsubscribe).toHaveBeenCalledOnce();
        return HttpResponse.json({ removed: 1 });
      }),
    );
    await login('account-b', 'test-password');
    expect(requests).toEqual([{ auth: 'Token account-a', body: { endpoint: 'https://push.example/current' } }]);
    expect(getToken()).toBe('account-b');
  });

  it('OAuth replacement unsubscribes locally even when server removal cannot connect', async () => {
    setToken('account-a');
    const { subscription } = installSubscription();
    server.use(http.post('*/api/push/unsubscribe/', () => HttpResponse.error()));
    await replaceSessionToken('oauth-account-b');
    expect(subscription.unsubscribe).toHaveBeenCalledOnce();
    expect(getToken()).toBe('oauth-account-b');
  });

  it('a late old logout cannot remove a replacement account endpoint', async () => {
    setToken('account-a');
    const { subscription, registration } = installSubscription();
    let finish;
    registration.pushManager.getSubscription.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = disconnectPushSession('account-a');
    await Promise.resolve();
    setToken('account-b');
    rememberPushBinding('account-b', subscription.endpoint);
    finish(subscription);
    expect(await pending).toBe(false);
    expect(subscription.unsubscribe).not.toHaveBeenCalled();
    expect(getToken()).toBe('account-b');
  });

  it('an external account change drops the old device but preserves an already verified new binding', async () => {
    const { subscription } = installSubscription();
    setToken('account-b');
    rememberPushBinding('account-b', subscription.endpoint);
    expect(await disconnectPushSession('account-a', { allowReplacement: true })).toBe(false);
    expect(subscription.unsubscribe).not.toHaveBeenCalled();
  });

  it('removes server ownership after a delayed bind even when native unsubscribe fails', async () => {
    setToken('delayed-binding-account');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    let finish;
    let started;
    const bindingStarted = new Promise((resolve) => { started = resolve; });
    const delayed = new Promise((resolve) => { finish = resolve; });
    let owner = null;
    const requests = [];
    server.use(
      http.post('*/api/push/subscribe/', async () => {
        started();
        await delayed;
        owner = 'old-account';
        requests.push('bind');
        return HttpResponse.json({ ok: true });
      }),
      http.post('*/api/push/unsubscribe/', () => {
        owner = null;
        requests.push('remove');
        return HttpResponse.json({ ok: true, removed: 1 });
      }),
    );
    const bind = bindPushSession(subscription, getToken());
    await bindingStarted;
    const removal = disconnectPushSession(getToken(), { stopSession: true });
    await Promise.resolve();
    expect(requests).toEqual([]);
    finish();
    expect(await bind).toBe(false);
    expect(await removal).toBe(true);
    expect(requests).toEqual(['bind', 'remove']);
    expect(owner).toBeNull();
  });

  it('blocks an offline switch when the live old endpoint cannot be removed', async () => {
    setToken('failed-removal-account');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    server.use(http.post('*/api/push/unsubscribe/', () => HttpResponse.error()));
    await expect(replaceSessionToken('new-account')).rejects.toThrow(/could not stop notifications/i);
    expect(getToken()).toBe('failed-removal-account');
  });

  it('clears logout credentials while surfacing an unresolved notification cleanup', async () => {
    setToken('failed-logout-account');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockRejectedValue(new Error('native unsubscribe failed'));
    server.use(
      http.post('*/api/auth/', () => HttpResponse.error()),
      http.post('*/api/push/unsubscribe/', () => HttpResponse.error()),
    );
    await expect(logout()).rejects.toThrow(/could not stop notifications/i);
    expect(getToken()).toBe('');
  });

  it('removes a deferred bind before revoking auth, and sends the captured device endpoint', async () => {
    setToken('ordered-revoke-account');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    let finish;
    let started;
    const pendingBind = new Promise((resolve) => { finish = resolve; });
    const startedBind = new Promise((resolve) => { started = resolve; });
    let tokenValid = true;
    let owner = null;
    const order = [];
    server.use(
      http.post('*/api/push/subscribe/', async () => {
        started();
        await pendingBind;
        owner = 'old-account';
        order.push('bind');
        return HttpResponse.json({ ok: true });
      }),
      http.post('*/api/push/unsubscribe/', () => {
        if (!tokenValid) return HttpResponse.json({ detail: 'Invalid token' }, { status: 401 });
        owner = null;
        order.push('remove');
        return HttpResponse.json({ ok: true, removed: 1 });
      }),
      http.post('*/api/auth/', async ({ request }) => {
        expect(await request.json()).toEqual({ action: 'logout', push_endpoint: subscription.endpoint });
        tokenValid = false;
        order.push('revoke');
        return HttpResponse.json({ ok: true });
      }),
    );
    const bind = bindPushSession(subscription, getToken());
    await startedBind;
    const removal = logout();
    finish();
    expect(await bind).toBe(false);
    await removal;
    expect(order).toEqual(['bind', 'remove', 'revoke']);
    expect(owner).toBeNull();
    expect(getToken()).toBe('');
  });

  it('does not trust removed:0 when the native endpoint is still live', async () => {
    setToken('unverified-owner-account');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    server.use(http.post('*/api/push/unsubscribe/', () => HttpResponse.json({ ok: true, removed: 0 })));
    await expect(replaceSessionToken('unverified-next-account')).rejects.toThrow(/could not stop notifications/i);
    expect(getToken()).toBe('unverified-owner-account');
  });

  it('does not trust a successful removal after an uncertain bind while native delivery remains live', async () => {
    setToken('uncertain-bind-account');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    server.use(
      http.post('*/api/push/subscribe/', () => HttpResponse.error()),
      http.post('*/api/push/unsubscribe/', () => HttpResponse.json({ ok: true, removed: 1 })),
    );
    await expect(bindPushSession(subscription, getToken())).rejects.toThrow(/connection/i);
    await expect(replaceSessionToken('uncertain-next-account')).rejects.toThrow(/could not stop notifications/i);
    expect(getToken()).toBe('uncertain-bind-account');
  });

  it('revokes the prior token before switching a still-live endpoint to another account', async () => {
    setToken('replace-with-revoke');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    const order = [];
    server.use(
      http.post('*/api/push/unsubscribe/', () => {
        order.push('remove');
        return HttpResponse.json({ ok: true, removed: 1 });
      }),
      http.post('*/api/auth/', async ({ request }) => {
        expect(request.headers.get('authorization')).toBe('Token replace-with-revoke');
        expect(await request.json()).toEqual({ action: 'logout', push_endpoint: subscription.endpoint });
        expect(getToken()).toBe('replace-with-revoke');
        order.push('revoke');
        return HttpResponse.json({ ok: true });
      }),
    );
    await replaceSessionToken('verified-next-account');
    expect(order).toEqual(['remove', 'revoke']);
    expect(getToken()).toBe('verified-next-account');
  });

  it('blocks switching a live endpoint if the old credential cannot be revoked', async () => {
    setToken('replace-revoke-failed');
    const { subscription } = installSubscription();
    subscription.unsubscribe.mockResolvedValue(false);
    server.use(
      http.post('*/api/push/unsubscribe/', () => HttpResponse.json({ ok: true, removed: 1 })),
      http.post('*/api/auth/', () => HttpResponse.error()),
    );
    await expect(replaceSessionToken('replacement-must-wait')).rejects.toThrow(/could not stop notifications/i);
    expect(getToken()).toBe('replace-revoke-failed');
  });
});
