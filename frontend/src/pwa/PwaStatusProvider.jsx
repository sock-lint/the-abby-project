import { useEffect, useRef, useState, useCallback } from 'react';
import { registerPromptWorker } from './registerPromptWorker';

import { STORAGE_KEYS } from '../constants/storage';
import { PwaStatusContext } from './pwaStatus.context';
import { isNativeRuntime } from '../platform/runtime';

// Safety-net delay: if `controllerchange` hasn't fired by then, force the
// reload anyway. iOS Safari PWAs and some Android browsers don't reliably
// fire the event after SKIP_WAITING, which leaves the banner visible
// indefinitely after the user clicks Reload.
const RELOAD_FALLBACK_MS = 1500;

// After the user clicks Reload we stash a timestamp in localStorage and
// swallow any onNeedRefresh that fires within this window on the next page
// load. Without this, environments with byte-level sw.js drift across
// requests (e.g. rolling deploys serving slightly different builds across
// replicas) re-fire onNeedRefresh on the fresh page within milliseconds —
// indistinguishable from "the banner never cleared" to the user.
const RELOAD_SUPPRESS_WINDOW_MS = 60_000;
const PWA_RELOAD_KEY = STORAGE_KEYS.PWA_LAST_RELOAD;

function recentlyAttemptedReload() {
  try {
    const raw = window.localStorage.getItem(PWA_RELOAD_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    if (!Number.isFinite(ts)) return false;
    return Date.now() - ts < RELOAD_SUPPRESS_WINDOW_MS;
  } catch {
    return false;
  }
}

function clearReloadAttempt() {
  try {
    window.localStorage.removeItem(PWA_RELOAD_KEY);
  } catch {
    // ignore — Safari private mode and similar throw on storage writes
  }
}

function markReloadAttempt() {
  try {
    window.localStorage.setItem(PWA_RELOAD_KEY, String(Date.now()));
  } catch {
    // ignore
  }
}

export function PwaStatusProvider({ children }) {
  const [updateReady, setUpdateReady] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const [updateBlocked, setUpdateBlocked] = useState(false);
  const [updateError, setUpdateError] = useState('');
  const updateSWRef = useRef(null);
  const guards = useRef(new Set());
  const updateRun = useRef(null);
  const needsReload = useRef(false);

  const registerUpdateGuard = useCallback((id, active) => {
    if (active) guards.current.add(id);
    else guards.current.delete(id);
    setUpdateBlocked(guards.current.size > 0);
  }, []);

  const stopUpdateRun = useCallback(() => {
    const run = updateRun.current;
    if (!run) return;
    clearTimeout(run.timer);
    navigator.serviceWorker?.removeEventListener('controllerchange', run.onControllerChange);
    updateRun.current = null;
  }, []);

  useEffect(() => {
    // Skip registration only in the actual `vite` dev server. In tests,
    // MODE === 'test' (with import.meta.env.DEV also true) — but we DO want
    // registration to run so the test mock can capture the callbacks.
    // In production, MODE === 'production' and registration proceeds.
    if (isNativeRuntime() || import.meta.env.MODE === 'development') return undefined;
    const sessionGuards = guards.current;
    const worker = registerPromptWorker({
      onNeedRefresh: () => {
        if (recentlyAttemptedReload()) {
          clearReloadAttempt();
          return;
        }
        setUpdateReady(true);
      },
      onOfflineReady: () => setOfflineReady(true),
      onRegisterError: () => setUpdateError('Could not prepare the app update. Try again later.'),
    });
    updateSWRef.current = worker.update;
    return () => {
      worker.dispose();
      updateSWRef.current = null;
      stopUpdateRun();
      sessionGuards.clear();
    };
  }, [stopUpdateRun]);

  const applyUpdate = useCallback(() => {
    if (isNativeRuntime() || import.meta.env.MODE === 'development') return false;
    if (guards.current.size > 0) {
      return false;
    }
    if (updateRun.current) return false;
    // Hide the banner while activation starts. The actual guarded reload
    // stamps the recent-attempt marker used by the next app boot.
    setUpdateReady(false);
    setUpdateError('');
    // Both worker control and the iOS timeout fallback use this one guarded
    // path. Registration itself never reloads the page.
    const run = { timer: null, onControllerChange: null };
    updateRun.current = run;
    const reload = () => {
      if (updateRun.current !== run) return;
      // New work can open after activation was requested. Keep it intact;
      // updating remains an explicit choice after its guard is released.
      if (guards.current.size > 0) {
        stopUpdateRun();
        setUpdateReady(true);
        return;
      }
      stopUpdateRun();
      markReloadAttempt();
      window.location.reload();
    };
    run.onControllerChange = () => {
      needsReload.current = true;
      reload();
    };
    if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
      navigator.serviceWorker.addEventListener('controllerchange', run.onControllerChange, {
        once: true,
      });
    }
    run.timer = setTimeout(reload, RELOAD_FALLBACK_MS);
    const fn = updateSWRef.current;
    Promise.resolve(needsReload.current ? true : typeof fn === 'function' ? fn() : false).then((started) => {
      if (started === true) needsReload.current = true;
      if (started !== false || updateRun.current !== run) return;
      stopUpdateRun();
      setUpdateReady(true);
      setUpdateError('Could not start the app update. Try again later.');
    }).catch(() => {
      if (updateRun.current !== run) return;
      stopUpdateRun();
      setUpdateReady(true);
      setUpdateError('Could not start the app update. Try again later.');
    });
    return true;
  }, [stopUpdateRun]);

  const dismissOfflineReady = useCallback(() => {
    setOfflineReady(false);
  }, []);

  return (
    <PwaStatusContext.Provider
      value={{ updateReady, offlineReady, updateBlocked, updateError, registerUpdateGuard, applyUpdate, dismissOfflineReady }}
    >
      {children}
    </PwaStatusContext.Provider>
  );
}

