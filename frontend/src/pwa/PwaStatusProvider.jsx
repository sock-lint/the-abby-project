import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { registerSW } from 'virtual:pwa-register';

const noop = () => {};

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
