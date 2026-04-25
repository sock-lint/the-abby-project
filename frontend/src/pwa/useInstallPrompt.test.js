import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useInstallPrompt } from './useInstallPrompt';

function fireBeforeInstallPrompt(promptFn = vi.fn(() => Promise.resolve()), choice = { outcome: 'accepted' }) {
  const event = new window.BeforeInstallPromptEvent('beforeinstallprompt', {
    prompt: promptFn,
    userChoice: Promise.resolve(choice),
  });
  // jsdom doesn't auto-prevent default on synthetic events; the hook calls
  // preventDefault() to suppress the browser's own banner. Stub it so the
  // call doesn't throw.
  event.preventDefault = vi.fn();
  window.dispatchEvent(event);
  return event;
}

function setMatchMedia(matches) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: query.includes('standalone') ? matches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe('useInstallPrompt', () => {
  beforeEach(() => {
    setMatchMedia(false);
    delete window.navigator.standalone;
  });

  it('starts with canInstall=false and isStandalone=false', () => {
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isStandalone).toBe(false);
  });

  it('captures beforeinstallprompt and flips canInstall to true', async () => {
    const { result } = renderHook(() => useInstallPrompt());
    act(() => {
      fireBeforeInstallPrompt();
    });
    await waitFor(() => expect(result.current.canInstall).toBe(true));
  });

  it('detects standalone via display-mode media query', () => {
    setMatchMedia(true);
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.isStandalone).toBe(true);
  });

  it('detects standalone via navigator.standalone (iOS)', () => {
    Object.defineProperty(window.navigator, 'standalone', {
      value: true,
      configurable: true,
    });
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.isStandalone).toBe(true);
  });

  it('install() calls event.prompt() and clears the captured event', async () => {
    const promptFn = vi.fn(() => Promise.resolve());
    const { result } = renderHook(() => useInstallPrompt());
    act(() => {
      fireBeforeInstallPrompt(promptFn);
    });
    await waitFor(() => expect(result.current.canInstall).toBe(true));
    await act(async () => {
      await result.current.install();
    });
    expect(promptFn).toHaveBeenCalledTimes(1);
    expect(result.current.canInstall).toBe(false);
  });

  it('install() is a no-op when no event has been captured', async () => {
    const { result } = renderHook(() => useInstallPrompt());
    await act(async () => {
      await result.current.install();
    });
    expect(result.current.canInstall).toBe(false);
  });

  it('preventDefault is called on the captured event', () => {
    const { result } = renderHook(() => useInstallPrompt());
    let event;
    act(() => {
      event = fireBeforeInstallPrompt();
    });
    expect(event.preventDefault).toHaveBeenCalled();
    expect(result.current).toBeDefined();
  });
});
