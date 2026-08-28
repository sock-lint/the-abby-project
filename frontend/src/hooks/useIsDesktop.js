import { useEffect, useState } from 'react';

/**
 * useIsDesktop — true at the `md` breakpoint and up. Lifted out of
 * BottomSheet when NotificationBell became the second surface that needs to
 * render a real bottom sheet on phones instead of a desktop popover.
 */
export default function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined') return true;
    return window.matchMedia('(min-width: 768px)').matches;
  });
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = (e) => setIsDesktop(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isDesktop;
}
