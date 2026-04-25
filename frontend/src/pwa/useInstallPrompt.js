import { useCallback, useEffect, useRef, useState } from 'react';

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

/**
 * useInstallPrompt — captures the browser's beforeinstallprompt event so
 * we can trigger the install prompt from a user gesture later (Settings
 * page "Install app" button). The event only fires once per page load,
 * so this hook should be mounted near the top of the tree (App.jsx).
 *
 * Returns:
 *   - canInstall: boolean, true when an install event has been captured
 *     and the user hasn't installed yet
 *   - install(): triggers the prompt; returns a Promise that resolves to
 *     the user's choice ('accepted'|'dismissed')
 *   - isStandalone: boolean, true when the app is already running as an
 *     installed PWA (display-mode: standalone or navigator.standalone)
 */
export function useInstallPrompt() {
  const [canInstall, setCanInstall] = useState(false);
  const [isStandalone, setIsStandalone] = useState(detectStandalone);
  const eventRef = useRef(null);

  useEffect(() => {
    function onBeforeInstallPrompt(event) {
      event.preventDefault();
      eventRef.current = event;
      setCanInstall(true);
    }
    function onAppInstalled() {
      eventRef.current = null;
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
    setCanInstall(false);
    return choice;
  }, []);

  return { canInstall, install, isStandalone };
}
