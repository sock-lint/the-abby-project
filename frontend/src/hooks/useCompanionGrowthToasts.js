import { useEffect, useState } from 'react';
import { markCompanionGrowthSeen } from '../api';
import { usePulse } from '../providers/pulseContext';

/**
 * Surfaces unseen companion auto-growth events (the silent daily tick
 * from PetService.auto_grow_companions). Returns a list of toast-ready
 * events plus a ``dismiss(petId)`` to drop a single one. The hook marks
 * the queue server-side seen as soon as the first non-empty payload
 * lands so a refresh doesn't re-show what the user already saw.
 *
 * Reads the shared heartbeat (PulseProvider) rather than its own timer.
 */
export function useCompanionGrowthToasts() {
  const { pulse } = usePulse();
  const [events, setEvents] = useState([]);

  useEffect(() => {
    if (!pulse) return;
    const list = Array.isArray(pulse.companion_growth?.events)
      ? pulse.companion_growth.events
      : [];
    if (list.length === 0) return;

    // Tag with a synthetic id (pet_id is present but multiple ticks for the
    // same pet across days are valid — combine pet + index for toast-stack
    // key uniqueness).
    const tagged = list.map((e, idx) => ({
      ...e,
      _toastId: `${e.pet_id ?? 'p'}-${e.new_growth ?? 0}-${idx}`,
    }));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- deriving toasts from each new heartbeat is the external-subscription case
    setEvents((prev) => {
      // De-dupe against currently-rendered toasts so a beat mid-render
      // doesn't double-stack.
      const existing = new Set(prev.map((p) => p._toastId));
      const next = tagged.filter((t) => !existing.has(t._toastId));
      return next.length ? [...prev, ...next] : prev;
    });
    // Server-side clear is fire-and-forget. If it fails we'll see the same
    // events on the next beat; the client de-dupe above keeps the UI stable.
    markCompanionGrowthSeen().catch(() => {});
  }, [pulse]);

  const dismiss = (toastId) =>
    setEvents((prev) => prev.filter((e) => e._toastId !== toastId));

  return { events, dismiss };
}
