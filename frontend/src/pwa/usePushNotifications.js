import { useCallback, useEffect, useState } from 'react';
import { getPushConfig, subscribeToPush, unsubscribeFromPush } from '../api';

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
  const supported = typeof window !== 'undefined'
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
    const load = async () => {
      try {
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
        if (!cancelled) setSubscribed(Boolean(existing));
      } catch {
        // Offline or unconfigured — the card renders its unavailable state.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [supported]);

  const subscribe = useCallback(async () => {
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
      const subscription = await registration.pushManager.subscribe({
        // Chrome refuses silent push outright; every notification we send is
        // user-visible anyway.
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      await subscribeToPush(subscription.toJSON());
      setSubscribed(true);
      return true;
    } catch (e) {
      setError(e?.message || 'Could not turn on notifications.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [publicKey]);

  const unsubscribe = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        // Tell the server first: if the local unsubscribe succeeded but the
        // API call didn't, we'd keep pushing to a dead endpoint until the
        // service 410s it.
        await unsubscribeFromPush(subscription.endpoint);
        await subscription.unsubscribe();
      }
      setSubscribed(false);
      return true;
    } catch (e) {
      setError(e?.message || 'Could not turn off notifications.');
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

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
