import { useEffect } from 'react';

// Deadlines only cause a server refresh; local time never authorizes a start
// or claim. Resume/focus also reconciles another device's completed action.
export default function useExpeditionRefresh(mounts, reload) {
  useEffect(() => {
    const refresh = () => { if (document.visibilityState !== 'hidden') void reload(); };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    const waits = mounts.flatMap((mount) => {
      const active = mount.active_expedition;
      if (active?.status === 'active' && !active.is_ready && Number.isFinite(active.seconds_remaining)) {
        return [active.seconds_remaining > 0 ? active.seconds_remaining * 1000 + 250 : 60000];
      }
      const wait = mount.expedition_available_in_seconds;
      return mount.expedition_available === false && Number.isFinite(wait)
        ? [wait > 0 ? wait * 1000 + 250 : 60000] : [];
    });
    const timer = waits.length ? setTimeout(refresh, Math.min(...waits, 2147483647)) : null;
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
      if (timer !== null) clearTimeout(timer);
    };
  }, [mounts, reload]);
}
