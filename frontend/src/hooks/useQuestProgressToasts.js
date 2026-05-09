import { useEffect, useRef, useState } from 'react';
import { getActiveQuest } from '../api';
import { useAuth } from './useApi';

const POLL_INTERVAL_MS = 25_000;

/**
 * Polls the active quest and emits a toast each time `current_progress`
 * advances. Backend already tracks the per-trigger progress delta inside
 * GameLoopService — this hook just diffs the polled snapshots so a child
 * who completed a chore on the dashboard sees a "+N toward Dragon Slayer"
 * floater regardless of which page they're on.
 *
 * Toast shape: `{ id, name, delta, percent }`
 *   - id: synthetic `${quest.id}-${current_progress}` so the same delta
 *     never re-toasts after a refresh.
 *   - name: definition.name (or "Quest" fallback).
 *   - delta: how many points were added in this poll cycle.
 *   - percent: rounded `progress_percent` post-update (0-100).
 *
 * Returns `{ toasts, dismiss }` — same contract as useDropToasts.
 *
 * Child-only by role gate; parents don't have personal active quests.
 */
export function useQuestProgressToasts(pollIntervalMs = POLL_INTERVAL_MS) {
  const { user } = useAuth();
  const [toasts, setToasts] = useState([]);
  const lastProgressRef = useRef(null);
  const lastQuestIdRef = useRef(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!user || user.role !== 'child') return undefined;
    let cancelled = false;

    const poll = async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const quest = await getActiveQuest();
        if (cancelled) return;

        // No active quest, or quest changed → reset baseline silently.
        if (!quest || !quest.id) {
          lastProgressRef.current = null;
          lastQuestIdRef.current = null;
          return;
        }

        const id = quest.id;
        const progress = Number(quest.current_progress || 0);

        if (
          !initializedRef.current ||
          lastQuestIdRef.current !== id
        ) {
          lastProgressRef.current = progress;
          lastQuestIdRef.current = id;
          initializedRef.current = true;
          return;
        }

        const prior = lastProgressRef.current ?? progress;
        const delta = progress - prior;
        if (delta > 0) {
          const name = quest.definition?.name || 'Quest';
          const percent = Math.min(100, Math.round(quest.progress_percent || 0));
          setToasts((prev) => [
            ...prev,
            {
              id: `${id}-${progress}`,
              name,
              delta,
              percent,
            },
          ]);
        }
        lastProgressRef.current = progress;
        lastQuestIdRef.current = id;
      } catch {
        // silent — caught next poll
      }
    };

    poll();
    const interval = setInterval(poll, pollIntervalMs);
    const onVisibility = () => {
      if (typeof document !== 'undefined' && !document.hidden) poll();
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
  }, [pollIntervalMs, user]);

  const dismiss = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return { toasts, dismiss };
}
