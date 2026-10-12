import { useCallback, useEffect, useRef } from 'react';
import { getToken } from '../../../api/client';

// Server mutations may commit after navigation or account replacement. Only
// the session that began the request may show its receipt or refresh its UI.
export default function usePetMutationGuard() {
  const mounted = useRef(true);
  const busy = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return useCallback(() => {
    if (busy.current) return null;
    busy.current = true;
    const token = getToken();
    return {
      isCurrent: () => mounted.current && getToken() === token,
      finish: () => { busy.current = false; },
    };
  }, []);
}
