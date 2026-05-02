/**
 * Single source of truth for every ``localStorage`` key the app reads or
 * writes. Importing from here instead of inlining string literals avoids
 * typo bugs (a misspelt key reads ``null`` silently and breaks features
 * in subtle ways) and gives a grep-able registry when you need to clear
 * or migrate a key.
 *
 * If you add a new key, document its purpose + lifetime here. The 401
 * self-heal path in ``api/client.js`` clears AUTH_TOKEN on demand;
 * everything else is best-effort cache.
 */
export const STORAGE_KEYS = {
  // DRF token. Cleared on 401 self-heal (see api/client.js) and on
  // explicit logout. Read by every authed API call.
  AUTH_TOKEN: 'abby_auth_token',

  // Per-section open/close state for the child dashboard accordions.
  // The full key is ``DASHBOARD_ACCORDION_PREFIX + slug(title)`` —
  // see components/dashboard/AccordionSection.jsx.
  DASHBOARD_ACCORDION_PREFIX: 'dashboard-accordion-',

  // Set of savings-goal IDs whose completion toast has already fired,
  // so we don't celebrate the same goal twice when the polling hook
  // re-evaluates. JSON-serialized array.
  SEEN_SAVINGS_COMPLETIONS: 'seenSavingsCompletions',

  // Sprite catalog JSON + the ETag we last saw — paired keys.
  // SpriteCatalogProvider revalidates on mount via If-None-Match.
  SPRITE_CATALOG: 'spriteCatalog',
  SPRITE_CATALOG_ETAG: 'spriteCatalogEtag',

  // Timestamp (Date.now() ms) of the last PWA service-worker reload
  // attempt. Used by PwaStatusProvider to suppress the update banner
  // for 60s after a reload, swallowing rolling-deploy SW drift across
  // replicas. See the PWA gotcha in CLAUDE.md.
  PWA_LAST_RELOAD: 'pwa:last-reload-attempt',
};
