import { createContext, useContext } from 'react';

/**
 * SpriteCatalogContext + useSpriteCatalog live here rather than beside the
 * provider component because `react-refresh/only-export-components` forbids
 * non-component exports from a `.jsx` file — the same rule that puts shared
 * constants in `<area>/<name>.constants.js` (see components/README.md).
 * Keeping them in a `.js` module lets SpriteCatalogProvider.jsx export only
 * its component, so Fast Refresh works on it.
 *
 * Both functions return null while the catalog is loading (cold first
 * mount); call sites already handle null via an emoji fallback.
 */
export const SpriteCatalogContext = createContext({
  getSpriteUrl: () => null,
  getSpriteMeta: () => null,
  refetchCatalog: () => Promise.resolve(),
});

export function useSpriteCatalog() {
  return useContext(SpriteCatalogContext);
}
