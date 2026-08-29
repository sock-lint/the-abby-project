import { createContext, useContext } from 'react';

/**
 * PwaStatusContext + usePwaStatus live here rather than beside the provider
 * component because `react-refresh/only-export-components` forbids
 * non-component exports from a `.jsx` file — the same rule that puts shared
 * constants in `<area>/<name>.constants.js` (see components/README.md).
 * Keeping them in a `.js` module lets PwaStatusProvider.jsx export only its
 * component, so Fast Refresh works on it.
 *
 * The defaults are deliberately safe outside a provider: nothing is waiting
 * and both actions are no-ops, so a component can call usePwaStatus()
 * unconditionally without a null check.
 */
const noop = () => {};

export const PwaStatusContext = createContext({
  updateReady: false,
  offlineReady: false,
  applyUpdate: noop,
  dismissOfflineReady: noop,
});

export function usePwaStatus() {
  return useContext(PwaStatusContext);
}
