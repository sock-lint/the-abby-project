import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, renderHook, screen, waitFor, act } from '@testing-library/react';
import { Capacitor } from '@capacitor/core';
import { registerSW } from 'virtual:pwa-register';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { PwaStatusProvider } from '../pwa/PwaStatusProvider';
import { usePwaStatus } from '../pwa/pwaStatus.context';
import { InstallPromptProvider, useInstallPrompt } from '../pwa/useInstallPrompt';
import { usePushNotifications } from '../pwa/usePushNotifications';
import { getPushRegistration, bindPushSession, disconnectPushSession } from '../pwa/pushSession';
import { logout, login } from '../api';
import { getToken } from '../api/client';
import { isNativeRuntime } from './runtime';

vi.mock('virtual:pwa-register', () => ({ registerSW: vi.fn() }));
const originalWorker = navigator.serviceWorker;

beforeEach(() => {
  vi.stubEnv('VITE_NATIVE_BUILD', 'true');
  vi.stubEnv('VITE_API_URL', 'https://staging.abby.example');
  vi.clearAllMocks();
  // A WebView can expose the worker property without having a ready worker.
  // Any accidental access fails instead of letting the test hang indefinitely.
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    get() { throw new Error('Browser service workers must not be accessed in native boot.'); },
  });
});

afterEach(() => {
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: originalWorker });
  delete window.__deferredInstallPrompt;
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

function PwaProbe() {
  const { updateReady, offlineReady, applyUpdate } = usePwaStatus();
  return <button onClick={applyUpdate}>{String(updateReady)} / {String(offlineReady)}</button>;
}

describe('native browser-service guards', () => {
  it('detects a real Capacitor runtime without requiring the build flag', () => {
    vi.stubEnv('VITE_NATIVE_BUILD', '');
    vi.spyOn(Capacitor, 'isNativePlatform').mockReturnValue(true);
    expect(isNativeRuntime()).toBe(true);
  });

  it('keeps worker/update state inactive and applyUpdate inert', () => {
    render(<PwaStatusProvider><PwaProbe /></PwaStatusProvider>);
    expect(registerSW).not.toHaveBeenCalled();
    const button = screen.getByRole('button', { name: 'false / false' });
    act(() => button.click());
    expect(localStorage.getItem('pwa:last-reload-attempt')).toBeNull();
  });

  it('ignores an existing browser install prompt and registers no install listener', async () => {
    window.__deferredInstallPrompt = { prompt: vi.fn() };
    const listener = vi.spyOn(window, 'addEventListener');
    const { result } = renderHook(() => useInstallPrompt(), { wrapper: InstallPromptProvider });
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isStandalone).toBe(true);
    await expect(result.current.install()).resolves.toEqual({ outcome: 'dismissed' });
    expect(listener.mock.calls.some(([name]) => name === 'beforeinstallprompt' || name === 'appinstalled')).toBe(false);
  });

  it('skips browser push initialization, subscription and teardown even with a token', async () => {
    const config = spyHandler('get', 'https://staging.abby.example/api/push/config/', { enabled: true });
    server.use(config.handler);
    const { result } = renderHook(() => usePushNotifications());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.supported).toBe(false);
    expect(result.current.enabled).toBe(false);
    expect(config.calls).toHaveLength(0);
    await expect(result.current.subscribe()).resolves.toBe(false);
    await expect(result.current.unsubscribe()).resolves.toBe(false);
    await expect(getPushRegistration()).resolves.toBeUndefined();
    await expect(bindPushSession({}, 'test-session')).resolves.toBe(false);
    await expect(disconnectPushSession()).resolves.toBe(true);
  });

  it('allows prototype login/logout without waiting for browser push readiness', async () => {
    const auth = spyHandler('post', 'https://staging.abby.example/api/auth/', ({ body }) =>
      body.action === 'login' ? { token: 'synthetic-native-session' } : { ok: true });
    server.use(auth.handler);
    await login('synthetic-child', 'synthetic-password');
    expect(getToken()).toBe('synthetic-native-session');
    await logout();
    expect(getToken()).toBe('');
    expect(auth.calls.map(({ body }) => body.action)).toEqual(['login', 'logout', 'logout']);
  });
});
