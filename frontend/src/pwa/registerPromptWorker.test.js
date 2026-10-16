import { afterEach, describe, expect, it, vi } from 'vitest';
import { registerPromptWorker } from './registerPromptWorker';

const original = navigator.serviceWorker;
afterEach(() => Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: original }));

function fixture({ controller = null, waiting = null, installing = null, active = null } = {}) {
  const registration = Object.assign(new EventTarget(), { waiting, installing, active });
  const container = Object.assign(new EventTarget(), { controller, register: vi.fn().mockResolvedValue(registration) });
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: container });
  return { registration, container };
}

function worker(state = 'installing') {
  return Object.assign(new EventTarget(), { state, postMessage: vi.fn() });
}

describe('Prompt-only browser worker registration', () => {
  it('recognizes an already waiting worker and sends only the fixed activation message', async () => {
    const waiting = worker('installed');
    const { container } = fixture({ waiting, controller: worker('activated') });
    const listen = vi.spyOn(container, 'addEventListener');
    const onNeedRefresh = vi.fn();
    const onOfflineReady = vi.fn();
    const prompt = registerPromptWorker({ onNeedRefresh, onOfflineReady });
    expect(await prompt.update()).toBe(true);
    expect(container.register).toHaveBeenCalledWith('/sw.js', { scope: '/' });
    expect(onNeedRefresh).toHaveBeenCalledTimes(1);
    expect(onOfflineReady).not.toHaveBeenCalled();
    expect(waiting.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' });
    // The helper never owns controllerchange/controlling or a reload path.
    expect(listen).not.toHaveBeenCalled();
    prompt.dispose();
  });

  it.each([false, true])('reports installation accurately with an existing controller: %s', async (replacing) => {
    const installing = worker();
    const { registration } = fixture({ controller: replacing ? worker('activated') : null });
    const onNeedRefresh = vi.fn();
    const onOfflineReady = vi.fn();
    const prompt = registerPromptWorker({ onNeedRefresh, onOfflineReady });
    expect(await prompt.update()).toBe(false);
    registration.installing = installing;
    registration.dispatchEvent(new Event('updatefound'));
    expect(onNeedRefresh).not.toHaveBeenCalled();
    expect(onOfflineReady).not.toHaveBeenCalled();
    installing.state = 'installed';
    installing.dispatchEvent(new Event('statechange'));
    expect(replacing ? onNeedRefresh : onOfflineReady).toHaveBeenCalledTimes(1);
    expect(replacing ? onOfflineReady : onNeedRefresh).not.toHaveBeenCalled();
    prompt.dispose();
    installing.dispatchEvent(new Event('statechange'));
    expect(replacing ? onNeedRefresh : onOfflineReady).toHaveBeenCalledTimes(1);
  });

  it('watches an installation already in progress when registration resolves', async () => {
    const installing = worker();
    fixture({ installing });
    const onOfflineReady = vi.fn();
    const prompt = registerPromptWorker({ onOfflineReady });
    await prompt.update();
    installing.state = 'installed';
    installing.dispatchEvent(new Event('statechange'));
    expect(onOfflineReady).toHaveBeenCalledTimes(1);
    prompt.dispose();
  });

  it('unsupported and failed registration never claim shell readiness or an update', async () => {
    const callbacks = { onOfflineReady: vi.fn(), onNeedRefresh: vi.fn(), onRegisterError: vi.fn() };
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: undefined });
    const unsupported = registerPromptWorker(callbacks);
    expect(await unsupported.update()).toBe(false);
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { register: vi.fn().mockRejectedValue(new Error('Registration failed')) } });
    const failed = registerPromptWorker(callbacks);
    expect(await failed.update()).toBe(false);
    expect(callbacks.onRegisterError).toHaveBeenCalledTimes(1);
    expect(callbacks.onOfflineReady).not.toHaveBeenCalled();
    expect(callbacks.onNeedRefresh).not.toHaveBeenCalled();
    unsupported.dispose();
    failed.dispose();
  });

  it('disposing before registration resolves prevents stale session callbacks and activation', async () => {
    let resolve;
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { register: () => new Promise((done) => { resolve = done; }) } });
    const onNeedRefresh = vi.fn();
    const prompt = registerPromptWorker({ onNeedRefresh });
    await Promise.resolve();
    prompt.dispose();
    const waiting = worker('installed');
    resolve({ waiting });
    expect(await prompt.update()).toBe(false);
    expect(onNeedRefresh).not.toHaveBeenCalled();
    expect(waiting.postMessage).not.toHaveBeenCalled();
  });
});
