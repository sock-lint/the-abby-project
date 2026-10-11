import { api, getToken, setToken } from '../api/client';
import { STORAGE_KEYS } from '../constants/storage';

function readBinding() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEYS.PUSH_SESSION)); } catch { return null; }
}

export function rememberPushBinding(token, endpoint) {
  try { localStorage.setItem(STORAGE_KEYS.PUSH_SESSION, JSON.stringify({ token, endpoint })); } catch { /* best effort */ }
}

export async function getPushRegistration() {
  return navigator.serviceWorker?.getRegistration?.('/');
}

let bindingQueue = Promise.resolve();
const stoppingSessions = new Set();
const uncertainBindings = new Set();

function queuePushOperation(operation) {
  const pending = bindingQueue.then(operation, operation);
  bindingQueue = pending.catch(() => false);
  return pending;
}

async function postPush(path, body, token, selfHeal = true) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    return await api.post(path, body, { token, signal: controller.signal, selfHeal });
  } finally { clearTimeout(timeout); }
}

export function bindPushSession(subscription, token) {
  const bind = async () => {
    if (!token || stoppingSessions.has(token) || getToken() !== token) return false;
    try {
      await postPush('/push/subscribe/', subscription.toJSON(), token);
    } catch (error) {
      // Aborting a request doesn't cancel an already authenticated server
      // handler. Require native removal before switching away from an
      // endpoint whose last server bind has an uncertain completion.
      if (error?.status === undefined) uncertainBindings.add(token);
      throw error;
    }
    if (stoppingSessions.has(token) || getToken() !== token) return false;
    rememberPushBinding(token, subscription.endpoint);
    return true;
  };
  // A previous account's slow request must finish before the current account
  // rebinds the same browser endpoint; its response cannot paint subscribed.
  return queuePushOperation(bind);
}

// Logout must stop this browser receiving the previous account's messages
// even without a connection. Delete only its endpoint, never other devices.
export async function disconnectPushSession(token = getToken(), {
  allowReplacement = false, stopSession = false, onEndpoint, onResult,
} = {}) {
  if (token) stoppingSessions.add(token);
  try {
    const registration = await getPushRegistration();
    const subscription = await registration?.pushManager?.getSubscription();
    if (!subscription) {
      onResult?.({ localRemoved: true, serverRemoved: false, endpoint: null });
      return true;
    }
    onEndpoint?.(subscription.endpoint);
    // A late logout must not unsubscribe a newer session's browser endpoint.
    if (getToken() && getToken() !== token) {
      const binding = readBinding();
      if (!allowReplacement || (binding?.endpoint === subscription.endpoint && binding.token !== token)) return false;
    }
    let localRemoved = false;
    try { localRemoved = await subscription.unsubscribe(); } catch { /* still remove server ownership */ }
    if (localRemoved) {
      uncertainBindings.delete(token);
      try { localStorage.removeItem(STORAGE_KEYS.PUSH_SESSION); } catch { /* best effort */ }
    }
    let serverRemoved = false;
    if (token) {
      try {
        const response = await queuePushOperation(() => postPush('/push/unsubscribe/', { endpoint: subscription.endpoint }, token, false));
        serverRemoved = response?.removed > 0 && !uncertainBindings.has(token);
      } catch {
        // A stopped local endpoint cannot deliver more push. The server prunes
        // expired endpoints on 404/410, so offline teardown stays successful.
      }
    }
    if (!localRemoved && !serverRemoved) {
      onResult?.({ localRemoved, serverRemoved, endpoint: subscription.endpoint });
      throw new Error('Could not stop notifications on this device. Reconnect and try again before switching accounts.');
    }
    onResult?.({ localRemoved, serverRemoved, endpoint: subscription.endpoint });
    return true;
  } finally {
    // Settings can opt back in without signing out. Logout/account replacement
    // keep their old credential stopped until a verified sign-in installs it.
    if (!stopSession) stoppingSessions.delete(token);
  }
}

export async function replaceSessionToken(token) {
  const previous = getToken();
  if (previous !== token) {
    let result;
    const stopped = await disconnectPushSession(previous, { stopSession: true, onResult: (value) => { result = value; } });
    if (!stopped || getToken() !== previous) throw new Error('The session changed. Please try signing in again.');
    if (previous) {
      try {
        await postPush('/auth/', {
          action: 'logout', ...(result?.endpoint ? { push_endpoint: result.endpoint } : {}),
        }, previous, false);
      } catch {
        if (!result?.localRemoved) {
          throw new Error('Could not stop notifications on this device. Reconnect and try again before switching accounts.');
        }
      }
      if (getToken() !== previous) throw new Error('The session changed. Please try signing in again.');
    }
  }
  stoppingSessions.delete(token);
  setToken(token);
}
