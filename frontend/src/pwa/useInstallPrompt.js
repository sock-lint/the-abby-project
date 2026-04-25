import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

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
  const [canInstall, setCanInstall] = useState(Boolean(stashed));
  const [isStandalone, setIsStandalone] = useState(detectStandalone);
  const eventRef = useRef(stashed);

  useEffect(() => {
    function onBeforeInstallPrompt(event) {
      event.preventDefault();
      eventRef.current = event;
      setCanInstall(true);
    }
    function onAppInstalled() {
      eventRef.current = null;
      if (typeof window !== 'undefined') window.__deferredInstallPrompt = null;
      setCanInstall(false);
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
    const event = eventRef.current;
    if (!event) return { outcome: 'dismissed' };
    await event.prompt();
    const choice = await event.userChoice;
    eventRef.current = null;
    if (typeof window !== 'undefined') window.__deferredInstallPrompt = null;
    setCanInstall(false);
    return choice;
  }, []);

  return React.createElement(
    InstallPromptContext.Provider,
    { value: { canInstall, install, isStandalone } },
    children,
  );
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
