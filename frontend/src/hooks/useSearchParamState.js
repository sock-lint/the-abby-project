import { useSearchParams } from 'react-router-dom';
import { useCallback } from 'react';

/**
 * Syncs a single filter value to a URL search param so filtered views are
 * bookmarkable. Uses the callback form of setSearchParams so sibling params
 * (e.g. ChapterHub's ?tab=) are never clobbered.
 *
 * @param {string} key       — the search-param name (e.g. 'status')
 * @param {string} defaultValue — value that means "no filter" (removed from URL)
 * @returns {[string, (v: string) => void]}
 */
export default function useSearchParamState(key, defaultValue = '') {
  const [params, setParams] = useSearchParams();
  const value = params.get(key) ?? defaultValue;

  const setValue = useCallback((newValue) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (newValue === defaultValue || newValue === '' || newValue == null) {
        next.delete(key);
      } else {
        next.set(key, newValue);
      }
      return next;
    }, { replace: true });
  }, [key, defaultValue, setParams]);

  return [value, setValue];
}
