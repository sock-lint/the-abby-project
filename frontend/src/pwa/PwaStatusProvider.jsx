import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { registerSW } from 'virtual:pwa-register';

const noop = () => {};

// Safety-net delay: if `controllerchange` hasn't fired by then, force the
// reload anyway. iOS Safari PWAs and some Android browsers don't reliably
// fire the event after SKIP_WAITING, which leaves the banner visible
// indefinitely after the user clicks Reload.
const RELOAD_FALLBACK_MS = 1500;

export const PwaStatusContext = createContext({
  updateReady: false,
  offlineReady: false,
  applyUpdate: noop,
  dismissOfflineReady: noop,
});

export function PwaStatusProvider({ children }) {
  const [updateReady, setUpdateReady] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const updateSWRef = useRef(null);

  useEffect(() => {
    // Skip registration only in the actual `vite` dev server. In tests,
    // MODE === 'test' (with import.meta.env.DEV also true) — but we DO want
    // registerSW to be called so the test mock can capture the callbacks.
    // In production, MODE === 'production' and registration proceeds.
    if (import.meta.env.MODE === 'development') return undefined;
    updateSWRef.current = registerSW({
      onNeedRefresh: () => setUpdateReady(true),
      onOfflineReady: () => setOfflineReady(true),
    });
    return undefined;
  }, []);

  const applyUpdate = useCallback(() => {
    const fn = updateSWRef.current;
    if (typeof fn === 'function') {
      fn(true);
    }
    // Own the reload instead of trusting vite-plugin-pwa's internal
    // controllerchange listener — that listener is unreliable on iOS Safari
    // PWAs and silently no-ops when there's no real waiting SW, which is
    // the failure mode behind "the banner is always there".
    let reloaded = false;
    const reload = () => {
      if (reloaded) return;
      reloaded = true;
      window.location.reload();
    };
    if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
      navigator.serviceWorker.addEventListener('controllerchange', reload, {
        once: true,
      });
    }
    setTimeout(reload, RELOAD_FALLBACK_MS);
  }, []);

  const dismissOfflineReady = useCallback(() => {
    setOfflineReady(false);
  }, []);

  return (
    <PwaStatusContext.Provider
      value={{ updateReady, offlineReady, applyUpdate, dismissOfflineReady }}
    >
      {children}
    </PwaStatusContext.Provider>
  );
}

export function usePwaStatus() {
  return useContext(PwaStatusContext);
}
