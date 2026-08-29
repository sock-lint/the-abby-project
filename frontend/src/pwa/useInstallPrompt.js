import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

function detectStandalone() {
  if (typeof window === 'undefined') return false;
  // iOS Safari uses navigator.standalone; Chrome/Edge/Firefox use the media
  // query. Both branches return true for an installed PWA.
  if (window.navigator?.standalone === true) return true;
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(display-mode: standalone)').matches;
  }
  return false;
}

const noop = () => Promise.resolve({ outcome: 'dismissed' });

const InstallPromptContext = createContext({
  canInstall: false,
  install: noop,
  isStandalone: false,
});

/**
 * InstallPromptProvider — mounts ONCE at the top of the tree (App.jsx) so
 * the window-level beforeinstallprompt listener is in place before the
 * browser fires the event (which only happens once per page load,
 * shortly after boot). Components deeper in the tree (e.g. InstallCard)
 * read the captured state via useInstallPrompt().
 */
function readStashedPrompt() {
  if (typeof window === 'undefined') return null;
  return window.__deferredInstallPrompt || null;
}

export function InstallPromptProvider({ children }) {
  const stashed = readStashedPrompt();
  // The deferred event is held in state, not a ref. Its presence IS
  // `canInstall`, so a ref plus a mirrored boolean was two sources for one
  // fact — and a callback closing over the ref trips react-hooks/refs, which
  // cannot prove the ref is never read during render.
  const [promptEvent, setPromptEvent] = useState(stashed);
  const [isStandalone, setIsStandalone] = useState(detectStandalone);
  const canInstall = Boolean(promptEvent);

  useEffect(() => {
    function onBeforeInstallPrompt(event) {
      event.preventDefault();
      setPromptEvent(event);
    }
    function onAppInstalled() {
      if (typeof window !== 'undefined') window.__deferredInstallPrompt = null;
      setPromptEvent(null);
      setIsStandalone(true);
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const install = useCallback(async () => {
    if (!promptEvent) return { outcome: 'dismissed' };
    await promptEvent.prompt();
    const choice = await promptEvent.userChoice;
    if (typeof window !== 'undefined') window.__deferredInstallPrompt = null;
    setPromptEvent(null);
    return choice;
  }, [promptEvent]);

  const value = useMemo(
    () => ({ canInstall, install, isStandalone }),
    [canInstall, install, isStandalone],
  );

  return React.createElement(InstallPromptContext.Provider, { value }, children);
}

/**
 * useInstallPrompt — reads the captured install-prompt state from the
 * InstallPromptProvider. Safe to call outside the provider (returns the
 * default no-op shape) so isolated component tests don't crash.
 */
export function useInstallPrompt() {
  return useContext(InstallPromptContext);
}

// Exported for tests that need to inject a custom context value without
// re-running the Provider's side-effectful useEffect.
export { InstallPromptContext };
