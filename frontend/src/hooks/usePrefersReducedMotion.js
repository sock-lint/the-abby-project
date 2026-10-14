import { useSyncExternalStore } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';
const getSnapshot = () => typeof window !== 'undefined' && Boolean(window.matchMedia?.(QUERY)?.matches);

function subscribe(onChange) {
  const query = window.matchMedia?.(QUERY);
  if (!query) return () => {};
  if (query.addEventListener) {
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }
  query.addListener?.(onChange);
  return () => query.removeListener?.(onChange);
}

// Keep preference changes reactive without replacing the mounted page/form.
export default function usePrefersReducedMotion() {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
