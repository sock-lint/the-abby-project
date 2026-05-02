import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { fetchSpriteCatalog } from '../api';

const SpriteCatalogContext = createContext({
  getSpriteUrl: () => null,
  getSpriteMeta: () => null,
  refetchCatalog: () => Promise.resolve(),
});

const STORAGE_KEY = 'spriteCatalog';
const ETAG_KEY = 'spriteCatalogEtag';

/**
 * Fetches the sprite catalog once at mount, caches it in localStorage
 * for warm mounts, and revalidates via ETag. Exposes getSpriteUrl (slug → url)
 * for shape compatibility with the old Vite-bundle map, plus getSpriteMeta
 * (slug → full metadata) for animated-sprite rendering.
 *
 * Returns null from both functions while the catalog is loading (cold first
 * mount) — existing call sites already handle null via emoji fallback.
 */
export function SpriteCatalogProvider({ children }) {
  const [catalog, setCatalog] = useState(() => {
    const cached = localStorage.getItem(STORAGE_KEY);
    if (!cached) return null;
    try {
      return JSON.parse(cached);
    } catch {
      return null;
    }
  });

  const refetchCatalog = useCallback(async ({ bypassEtag = false } = {}) => {
    try {
      const prevEtag = bypassEtag ? null : localStorage.getItem(ETAG_KEY);
      const resp = await fetchSpriteCatalog(prevEtag);
      if (resp.notModified) return;
      setCatalog(resp);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(resp));
      localStorage.setItem(ETAG_KEY, resp.etag);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('sprite catalog fetch failed', err);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const prevEtag = localStorage.getItem(ETAG_KEY);
    fetchSpriteCatalog(prevEtag, { signal: controller.signal })
      .then((resp) => {
        if (controller.signal.aborted) return;
        if (resp.notModified) return;
        setCatalog(resp);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(resp));
        localStorage.setItem(ETAG_KEY, resp.etag);
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        // eslint-disable-next-line no-console
        console.error('sprite catalog fetch failed', err);
      });
    return () => controller.abort();
  }, []);

  // Emit the shared @keyframes sprite-cycle rule when the catalog contains
  // any animated sprite. Per-sprite particulars (frame count, element size)
  // are injected inline via the --sprite-end-x CSS custom property.
  useEffect(() => {
    if (!catalog) return;
    const hasAnimated = Object.values(catalog.sprites || {}).some((s) => s.frames > 1);
    if (!hasAnimated) return;

    const rule = `@keyframes sprite-cycle { to { background-position-x: var(--sprite-end-x, 0); } }`;
    let tag = document.getElementById('sprite-keyframes');
    if (!tag) {
      tag = document.createElement('style');
      tag.id = 'sprite-keyframes';
      document.head.appendChild(tag);
    }
    tag.textContent = rule;
  }, [catalog]);

  const value = useMemo(() => ({
    getSpriteUrl: (slug) => (catalog?.sprites?.[slug]?.url ?? null),
    getSpriteMeta: (slug) => (catalog?.sprites?.[slug] ?? null),
    refetchCatalog,
  }), [catalog, refetchCatalog]);

  return (
    <SpriteCatalogContext.Provider value={value}>
      {children}
    </SpriteCatalogContext.Provider>
  );
}

export function useSpriteCatalog() {
  return useContext(SpriteCatalogContext);
}
