import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { fetchSpriteCatalog } from '../api';

const SpriteCatalogContext = createContext({
  getSpriteUrl: () => null,
  getSpriteMeta: () => null,
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

  useEffect(() => {
    let cancelled = false;
    const prevEtag = localStorage.getItem(ETAG_KEY);
    fetchSpriteCatalog(prevEtag)
      .then((resp) => {
        if (cancelled) return;
        if (resp.notModified) return; // cached catalog is still good
        setCatalog(resp);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(resp));
        localStorage.setItem(ETAG_KEY, resp.etag);
      })
      .catch((err) => {
        // Network failure on cold start — let call sites emoji-fallback.
        // Don't clear cached data; a stale catalog still beats no catalog.
        // console.error so Sentry captures the regression in production.
        // eslint-disable-next-line no-console
        console.error('sprite catalog fetch failed', err);
      });
    return () => { cancelled = true; };
  }, []);

  // Emit @keyframes for each distinct frame_count present in the catalog.
  // One <style id="sprite-keyframes"> tag; one rule per distinct count.
  useEffect(() => {
    if (!catalog) return;
    const counts = new Set();
    Object.values(catalog.sprites || {}).forEach((s) => {
      if (s.frames > 1) counts.add(s.frames);
    });
    if (counts.size === 0) return;

    const rules = Array.from(counts).sort().map((n) => {
      // Width translation — background-position moves by -100% of the strip
      // width to cycle through all frames. Using percent lets the keyframe
      // work at any render size.
      return `@keyframes sprite-cycle-${n} { from { background-position: 0 0 } to { background-position: -100% 0 } }`;
    }).join('\n');

    let tag = document.getElementById('sprite-keyframes');
    if (!tag) {
      tag = document.createElement('style');
      tag.id = 'sprite-keyframes';
      document.head.appendChild(tag);
    }
    tag.textContent = rules;
  }, [catalog]);

  const value = useMemo(() => ({
    getSpriteUrl: (slug) => (catalog?.sprites?.[slug]?.url ?? null),
    getSpriteMeta: (slug) => (catalog?.sprites?.[slug] ?? null),
  }), [catalog]);

  return (
    <SpriteCatalogContext.Provider value={value}>
      {children}
    </SpriteCatalogContext.Provider>
  );
}

export function useSpriteCatalog() {
  return useContext(SpriteCatalogContext);
}
