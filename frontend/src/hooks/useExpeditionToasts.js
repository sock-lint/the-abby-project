import { useCallback, useEffect, useState } from 'react';
import { listExpeditions } from '../api';

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
 * useExpeditionToasts — polls /api/expeditions/?ready=true every 60s and
 * surfaces ready-to-claim mounts as a soft "your mount is back" nudge.
 *
 * Dismissals are persisted in localStorage so a refresh doesn't re-show
 * the same nudge. The actual claim happens on the Mounts page — the
 * toast just routes the user there with a deep-link, mirroring how
 * approval toasts route to the queue.
 *
 * Returns ``{ ready, dismiss }`` where ``ready`` is the list of
 * ready-to-claim expeditions filtered against the dismissed set.
 */
export function useExpeditionToasts(pollIntervalMs = 60000) {
  const [ready, setReady] = useState([]);
  const [dismissed, setDismissed] = useState(() => loadSeen());

  const poll = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    try {
      const res = await listExpeditions(true);
      const list = Array.isArray(res?.expeditions) ? res.expeditions : [];
      setReady(list);
    } catch {
      // silent fail — never break the app for a poll error
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
