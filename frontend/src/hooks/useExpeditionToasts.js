import { useCallback, useState } from 'react';
import { usePulse } from '../providers/pulseContext';

const READY_SEEN_KEY = 'abby:expeditions:dismissed';

function loadSeen() {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.localStorage.getItem(READY_SEEN_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function persistSeen(set) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(READY_SEEN_KEY, JSON.stringify([...set]));
  } catch {
    // localStorage full / disabled — silent fail keeps the UI working,
    // worst case a user dismisses the same nudge twice.
  }
}

/**
 * useExpeditionToasts — surfaces ready-to-claim mounts from the shared
 * heartbeat as a soft "your mount is back" nudge.
 *
 * Dismissals are persisted in localStorage so a refresh doesn't re-show
 * the same nudge. The actual claim happens on the Mounts page — the
 * toast just routes the user there with a deep-link, mirroring how
 * approval toasts route to the queue.
 *
 * Returns ``{ ready, dismiss }`` where ``ready`` is the list of
 * ready-to-claim expeditions filtered against the dismissed set.
 */
export function useExpeditionToasts() {
  const { pulse } = usePulse();
  const [dismissed, setDismissed] = useState(() => loadSeen());

  const ready = Array.isArray(pulse?.expeditions_ready) ? pulse.expeditions_ready : [];

  const dismiss = useCallback((expeditionId) => {
    setDismissed((prev) => {
      if (prev.has(expeditionId)) return prev;
      const next = new Set(prev);
      next.add(expeditionId);
      persistSeen(next);
      return next;
    });
  }, []);

  return {
    ready: ready.filter((e) => !dismissed.has(e.id)),
    dismiss,
  };
}
