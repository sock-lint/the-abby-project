import { useEffect, useRef } from 'react';

// A completed request from an old account/child workspace must not navigate
// or start another request after its keyed owner has unmounted.
export default function useMountedRef() {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return mounted;
}
