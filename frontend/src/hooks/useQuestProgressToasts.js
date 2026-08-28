import { useEffect, useRef, useState } from 'react';
import { usePulse } from '../providers/pulseContext';
import { useAuth } from './useApi';

/**
 * Watches the shared heartbeat and emits a toast each time the active
 * quest's `current_progress` advances. Backend already tracks the per-trigger progress delta inside
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
export function useQuestProgressToasts() {
  const { user } = useAuth();
  const { pulse } = usePulse();
  const [toasts, setToasts] = useState([]);
  const lastProgressRef = useRef(null);
  const lastQuestIdRef = useRef(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!pulse) return;
    if (!user || user.role !== 'child') return;

    const quest = pulse.active_quest;

    // No active quest, or quest changed → reset baseline silently.
    if (!quest || !quest.id) {
      lastProgressRef.current = null;
      lastQuestIdRef.current = null;
      return;
    }

    const id = quest.id;
    const progress = Number(quest.current_progress || 0);

    if (!initializedRef.current || lastQuestIdRef.current !== id) {
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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- deriving toasts from each new heartbeat is exactly the external-subscription case
      setToasts((prev) => [...prev, { id: `${id}-${progress}`, name, delta, percent }]);
    }
    lastProgressRef.current = progress;
    lastQuestIdRef.current = id;
  }, [pulse, user]);

  const dismiss = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return { toasts, dismiss };
}
