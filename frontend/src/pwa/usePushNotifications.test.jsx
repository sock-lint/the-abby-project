import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { usePushNotifications, urlBase64ToUint8Array } from './usePushNotifications';

const REAL = {
  serviceWorker: navigator.serviceWorker,
  PushManager: window.PushManager,
  Notification: window.Notification,
};

/** Install a fake browser push stack. */
function installPushApis({ permission = 'default', existing = null } = {}) {
  const subscription = {
    endpoint: 'https://push.example/abc',
    toJSON: () => ({
      endpoint: 'https://push.example/abc',
      keys: { p256dh: 'p', auth: 'a' },
    }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  };
  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(existing),
    subscribe: vi.fn().mockResolvedValue(subscription),
  };
  Object.defineProperty(navigator, 'serviceWorker', {
    value: { ready: Promise.resolve({ pushManager }) },
    configurable: true,
  });
  window.PushManager = function PushManagerStub() {};
  window.Notification = {
    permission,
    requestPermission: vi.fn().mockResolvedValue(permission === 'default' ? 'granted' : permission),
  };
  return { pushManager, subscription };
}

function removePushApis() {
  Object.defineProperty(navigator, 'serviceWorker', { value: undefined, configurable: true });
  delete window.PushManager;
  delete window.Notification;
}

beforeEach(() => {
  server.use(
    http.get('*/api/push/config/', () =>
      HttpResponse.json({ enabled: true, public_key: 'BEl62iUYgUivxIkv69yViEuiBIa40HI' }),
    ),
  );
});

afterEach(() => {
  Object.defineProperty(navigator, 'serviceWorker', { value: REAL.serviceWorker, configurable: true });
  window.PushManager = REAL.PushManager;
  window.Notification = REAL.Notification;
  vi.restoreAllMocks();
});

describe('urlBase64ToUint8Array', () => {
  it('decodes an unpadded base64url VAPID key to bytes', () => {
    const bytes = urlBase64ToUint8Array('BEl62iUYgUivxIkv69yViEuiBIa40HI');
    expect(bytes).toBeInstanceOf(Uint8Array);
    expect(bytes.length).toBeGreaterThan(0);
  });

  it('handles the -/_ alphabet', () => {
    // '-' and '_' stand in for '+' and '/' in base64url; both must decode.
    const bytes = urlBase64ToUint8Array('a-b_cw');
    expect(bytes).toBeInstanceOf(Uint8Array);
    expect(bytes.length).toBe(4);
  });
});

describe('usePushNotifications', () => {
  it('reports unsupported when the browser has no push APIs', async () => {
    removePushApis();
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.supported).toBe(false);
  });

  it('reports the server as disabled when no keypair is configured', async () => {
    installPushApis();
    server.use(
      http.get('*/api/push/config/', () =>
        HttpResponse.json({ enabled: false, public_key: '' }),
      ),
    );
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.enabled).toBe(false);
  });

  it('detects an existing subscription on mount', async () => {
    installPushApis({ existing: { endpoint: 'https://push.example/abc' } });
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.subscribed).toBe(true));
  });

  it('subscribing asks permission and POSTs the browser subscription', async () => {
    const spy = spyHandler('post', /\/api\/push\/subscribe\/$/, { ok: true });
    server.use(spy.handler);
    const { pushManager } = installPushApis();
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => { await result.current.subscribe(); });

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toMatchObject({
      endpoint: 'https://push.example/abc',
      keys: { p256dh: 'p', auth: 'a' },
    });
    // Chrome rejects silent push outright.
    expect(pushManager.subscribe).toHaveBeenCalledWith(
      expect.objectContaining({ userVisibleOnly: true }),
    );
    expect(result.current.subscribed).toBe(true);
  });

  it('surfaces a clear message when the user blocks the prompt', async () => {
    installPushApis();
    window.Notification.requestPermission = vi.fn().mockResolvedValue('denied');
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => { await result.current.subscribe(); });

    expect(result.current.subscribed).toBe(false);
    expect(result.current.permission).toBe('denied');
    expect(result.current.error).toMatch(/blocked/i);
  });

  it('unsubscribing tells the server before dropping the local subscription', async () => {
    const spy = spyHandler('post', /\/api\/push\/unsubscribe\/$/, { ok: true });
    server.use(spy.handler);
    const existing = {
      endpoint: 'https://push.example/abc',
      unsubscribe: vi.fn().mockResolvedValue(true),
    };
    installPushApis({ permission: 'granted', existing });
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.subscribed).toBe(true));

    await act(async () => { await result.current.unsubscribe(); });

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ endpoint: 'https://push.example/abc' });
    expect(existing.unsubscribe).toHaveBeenCalled();
    expect(result.current.subscribed).toBe(false);
  });
});
