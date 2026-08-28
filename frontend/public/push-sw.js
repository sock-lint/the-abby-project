/* global clients */
/**
 * Web Push handlers, imported into the generated service worker via
 * workbox's `importScripts` (see vite.config.js).
 *
 * Deliberately NOT using vite-plugin-pwa's `injectManifest` strategy: that
 * would mean hand-owning the whole service worker, and the precache +
 * update-prompt behavior documented in frontend/CLAUDE.md is load-bearing
 * (the SKIP_WAITING reload dance, the no-cache header on sw.js). Importing a
 * small script keeps generateSW in charge of everything it already handles.
 */

// The payload shape comes from apps/notifications/push.py::send_to_user.
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    // A malformed or empty payload still deserves a nudge rather than
    // nothing — the bell has the detail.
  }

  const title = data.title || 'The Abby Project';
  const options = {
    body: data.body || '',
    icon: '/pwa-192x192.png',
    badge: '/pwa-192x192.png',
    // Collapse repeats of the same kind so a burst of approvals doesn't
    // stack six separate banners on the lock screen.
    tag: data.type || 'abby',
    renotify: true,
    data: { url: data.url || '/' },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';

  // Focus an already-open window rather than piling up tabs; only fall back
  // to opening one when the app isn't running.
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if ('focus' in client) {
          if ('navigate' in client) client.navigate(target);
          return client.focus();
        }
      }
      return clients.openWindow ? clients.openWindow(target) : undefined;
    }),
  );
});
