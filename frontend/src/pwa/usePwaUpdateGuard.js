import { useId, useLayoutEffect } from 'react';
import { usePwaStatus } from './pwaStatus.context';

// A guard records only whether open work needs protection. No form values,
// identities, credentials or draft bodies enter the shared registry.
export function usePwaUpdateGuard(active) {
  const id = useId();
  const { registerUpdateGuard } = usePwaStatus();
  useLayoutEffect(() => {
    if (typeof registerUpdateGuard !== 'function') return undefined;
    registerUpdateGuard(id, Boolean(active));
    return () => registerUpdateGuard(id, false);
  }, [id, active, registerUpdateGuard]);
}
