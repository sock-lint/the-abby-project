import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { getPushConfig } from '../api';
import { AUTH_CHANGED_EVENT, getToken } from '../api/client';
import { bindPushSession, disconnectPushSession } from './pushSession';
import { isNativeRuntime } from '../platform/runtime';

function watchSession(onChange) {
  window.addEventListener(AUTH_CHANGED_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

/**
 * usePushNotifications — opt this browser in or out of Web Push.
 *
 * The submit-then-approve loop only moves when someone opens the app; this
 * is what lets a kid's homework submission reach a parent's lock screen.
 *
 * Degrades in layers, so the UI can always say something true:
 *   - `supported` false  → this browser has no push/service-worker/Notification
 *     API at all (desktop Safari, in-app webviews, iOS before 16.4 or when
 *     the app isn't installed to the home screen).
 *   - `enabled` false    → the SERVER has no VAPID keypair; nothing to offer.
 *   - `permission`       → the browser's own 'default' | 'granted' | 'denied'.
 *     A 'denied' can only be undone in browser settings, never by us.
 */
export function usePushNotifications() {
  const token = useSyncExternalStore(watchSession, getToken, () => '');
  const native = isNativeRuntime();
  const supported = !native && typeof window !== 'undefined'
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && 'Notification' in window;

  const [enabled, setEnabled] = useState(false);
  const [publicKey, setPublicKey] = useState('');
  const [subscribed, setSubscribed] = useState(false);
  const [permission, setPermission] = useState(
    supported ? Notification.permission : 'denied',
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setSubscribed(false);
    setLoading(true);
    setError('');
    const load = async () => {
      try {
        if (native || !token) return;
        // Fetch the config even on a browser that can't subscribe: the card
        // needs to know the server offers push at all before it can explain
        // *why* this device can't use it (the iPhone "install it first" case).
        const config = await getPushConfig();
        if (cancelled) return;
        setEnabled(Boolean(config?.enabled));
        setPublicKey(config?.public_key || '');

        if (!supported) return;
        const registration = await navigator.serviceWorker.ready;
        const existing = await registration.pushManager.getSubscription();
        if (existing && config?.enabled && !cancelled) {
          const bound = await bindPushSession(existing, token);
          if (!cancelled) setSubscribed(bound);
        }
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not verify notifications for this account.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [native, supported, token]);

  const subscribe = useCallback(async () => {
    if (isNativeRuntime() || !supported) return false;
    if (!token || getToken() !== token) return false;
    setBusy(true);
    setError('');
    try {
      // Must be called from a user gesture or browsers reject it outright.
      const granted = await Notification.requestPermission();
      setPermission(granted);
      if (granted !== 'granted') {
        setError(
          granted === 'denied'
            ? 'Notifications are blocked for this site — turn them back on in your browser settings.'
            : 'Notifications were not enabled.',
        );
        return false;
      }

      const registration = await navigator.serviceWorker.ready;
      if (getToken() !== token) return false;
      const subscription = await registration.pushManager.subscribe({
        // Chrome refuses silent push outright; every notification we send is
        // user-visible anyway.
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      const bound = await bindPushSession(subscription, token);
      if (getToken() === token) setSubscribed(bound);
      return bound;
    } catch (e) {
      setError(e?.message || 'Could not turn on notifications.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [publicKey, supported, token]);

  const unsubscribe = useCallback(async () => {
    if (isNativeRuntime()) return false;
    setBusy(true);
    setError('');
    try {
      const removed = await disconnectPushSession(token);
      if (!removed) throw new Error('Could not turn off notifications on this device. Try again.');
      if (getToken() === token) setSubscribed(false);
      return removed;
    } catch (e) {
      setError(e?.message || 'Could not turn off notifications.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [token]);

  return {
    supported, enabled, subscribed, permission, busy, error, loading,
    subscribe, unsubscribe,
  };
}

/**
 * VAPID keys travel as base64url text; pushManager.subscribe wants raw bytes.
 */
export function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}
