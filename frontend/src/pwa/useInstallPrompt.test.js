import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { InstallPromptProvider, useInstallPrompt } from './useInstallPrompt';

function fireBeforeInstallPrompt(promptFn = vi.fn(() => Promise.resolve()), choice = { outcome: 'accepted' }) {
  const event = new window.BeforeInstallPromptEvent('beforeinstallprompt', {
    prompt: promptFn,
    userChoice: Promise.resolve(choice),
  });
  event.preventDefault = vi.fn();
  window.dispatchEvent(event);
  return event;
}

function fireAppInstalled() {
  window.dispatchEvent(new Event('appinstalled'));
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

function wrapper({ children }) {
  return React.createElement(InstallPromptProvider, null, children);
}

describe('useInstallPrompt', () => {
  beforeEach(() => {
    setMatchMedia(false);
    delete window.navigator.standalone;
  });

  it('starts with canInstall=false and isStandalone=false', () => {
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isStandalone).toBe(false);
  });

  it('captures beforeinstallprompt and flips canInstall to true', async () => {
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    act(() => {
      fireBeforeInstallPrompt();
    });
    await waitFor(() => expect(result.current.canInstall).toBe(true));
  });

  it('detects standalone via display-mode media query', () => {
    setMatchMedia(true);
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    expect(result.current.isStandalone).toBe(true);
  });

  it('detects standalone via navigator.standalone (iOS)', () => {
    Object.defineProperty(window.navigator, 'standalone', {
      value: true,
      configurable: true,
    });
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    expect(result.current.isStandalone).toBe(true);
  });

  it('install() calls event.prompt() and clears the captured event', async () => {
    const promptFn = vi.fn(() => Promise.resolve());
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
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
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    await act(async () => {
      await result.current.install();
    });
    expect(result.current.canInstall).toBe(false);
  });

  it('preventDefault is called on the captured event', () => {
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    let event;
    act(() => {
      event = fireBeforeInstallPrompt();
    });
    expect(event.preventDefault).toHaveBeenCalled();
    expect(result.current).toBeDefined();
  });

  it('appinstalled event flips canInstall back to false and isStandalone to true', async () => {
    const { result } = renderHook(() => useInstallPrompt(), { wrapper });
    // First capture an install event
    act(() => {
      fireBeforeInstallPrompt();
    });
    await waitFor(() => expect(result.current.canInstall).toBe(true));
    expect(result.current.isStandalone).toBe(false);

    // Then simulate the browser firing `appinstalled` after the user installs
    act(() => {
      fireAppInstalled();
    });
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isStandalone).toBe(true);
  });

  it('returns safe defaults when used outside the provider', () => {
    // Don't crash; just expose the no-op shape so isolated component tests
    // that don't wrap in the provider still work.
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isStandalone).toBe(false);
    // install() shouldn't throw
    return expect(result.current.install()).resolves.toMatchObject({
      outcome: 'dismissed',
    });
  });
});
