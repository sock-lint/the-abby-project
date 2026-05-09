import { useEffect, useState, useCallback } from 'react';
import { getRecentCompanionGrowth, markCompanionGrowthSeen } from '../api';

/**
 * Polls for unseen companion auto-growth events (the silent daily tick
 * from PetService.auto_grow_companions). Returns a list of toast-ready
 * events plus a ``dismiss(petId)`` to drop a single one. The hook marks
 * the queue server-side seen as soon as the first non-empty payload
 * lands so a refresh doesn't re-show what the user already saw.
 *
 * Mirrors useDropToasts: 20s polling, visibility-aware, silent-fail.
 */
export function useCompanionGrowthToasts(pollIntervalMs = 20000) {
  const [events, setEvents] = useState([]);

  const poll = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    try {
      const res = await getRecentCompanionGrowth();
      const list = Array.isArray(res?.events) ? res.events : [];
      if (list.length === 0) return;
      // Tag with a synthetic id (pet_id is present but multiple ticks for
      // the same pet across days are valid — combine pet + index for
      // toast-stack key uniqueness).
      const tagged = list.map((e, idx) => ({
        ...e,
        _toastId: `${e.pet_id ?? 'p'}-${e.new_growth ?? 0}-${idx}`,
      }));
      setEvents((prev) => {
        // De-dupe against currently-rendered toasts so a poll mid-render
        // doesn't double-stack.
        const existing = new Set(prev.map((p) => p._toastId));
        const next = tagged.filter((t) => !existing.has(t._toastId));
        return next.length ? [...prev, ...next] : prev;
      });
      // Server-side clear is fire-and-forget. If it fails we'll just see
      // the same events on the next poll; client de-dupe above keeps the
      // UI stable.
      markCompanionGrowthSeen().catch(() => {});
    } catch {
      // silent fail — don't break the app for a poll
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const safePoll = () => { if (!cancelled) poll(); };
    safePoll();
    const interval = setInterval(safePoll, pollIntervalMs);
    const onVisibility = () => {
      if (typeof document !== 'undefined' && !document.hidden) safePoll();
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibility);
    }
    return () => {
      cancelled = true;
      clearInterval(interval);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, [pollIntervalMs, poll]);

  const dismiss = (toastId) =>
    setEvents((prev) => prev.filter((e) => e._toastId !== toastId));

  return { events, dismiss };
}
