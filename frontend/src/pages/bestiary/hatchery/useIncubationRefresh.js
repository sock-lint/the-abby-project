import { useEffect } from 'react';

// A deadline triggers a read, never a hatch. Refresh on resume as another
// device may have started or finished the account's single incubation.
export default function useIncubationRefresh(incubation, reload) {
  useEffect(() => {
    const refresh = () => { if (document.visibilityState !== 'hidden') void reload(); };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    const seconds = incubation?.remaining_seconds;
    const wait = incubation && !incubation.is_ready && Number.isFinite(seconds)
      ? seconds > 0 ? seconds * 1000 + 250 : 60000 : null;
    const timer = wait === null ? null : setTimeout(refresh, Math.min(wait, 2147483647));
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
      if (timer !== null) clearTimeout(timer);
    };
  }, [incubation, reload]);
}
