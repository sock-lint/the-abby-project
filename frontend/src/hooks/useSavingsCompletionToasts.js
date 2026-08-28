import { useState, useEffect, useRef } from 'react';
import { STORAGE_KEYS } from '../constants/storage';
import { normalizeList } from '../utils/api';
import { usePulse } from '../providers/pulseContext';

const STORAGE_KEY = STORAGE_KEYS.SEEN_SAVINGS_COMPLETIONS;
const COINS_PER_DOLLAR = 2;

function loadSeen() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function persistSeen(set) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    // Storage quota / privacy mode — silent fail; worst case we re-show
    // the same toast once per session, which is harmless.
  }
}

/**
 * Watches the shared heartbeat and emits a toast the first time we observe
 * a newly-completed savings goal. Seen IDs persist in localStorage so we don't
 * re-toast a goal the child already saw on a prior page load.
 *
 * Returns `{ toasts, dismiss }` — same contract as `useDropToasts`.
 * Toast shape: `{ id, title, icon, coin_bonus }`.
 */
export function useSavingsCompletionToasts() {
  const { pulse } = usePulse();
  const [toasts, setToasts] = useState([]);
  const seenRef = useRef(loadSeen());
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!pulse) return;
    const goals = normalizeList(pulse.savings_goals);
    const completed = goals.filter((g) => g.is_completed && g.id != null);

    if (!initializedRef.current) {
      for (const g of completed) seenRef.current.add(g.id);
      persistSeen(seenRef.current);
      initializedRef.current = true;
      return;
    }

    const fresh = completed.filter((g) => !seenRef.current.has(g.id));
    if (fresh.length === 0) return;

    for (const g of fresh) seenRef.current.add(g.id);
    persistSeen(seenRef.current);

    setToasts((prev) => [
      ...prev,
      ...fresh.map((g) => ({
        id: `savings-${g.id}`,
        title: g.title,
        icon: g.icon || '🏆',
        coin_bonus: Math.round(Number(g.target_amount || 0) * COINS_PER_DOLLAR),
      })),
    ]);
  }, [pulse]);

  const dismiss = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return { toasts, dismiss };
}
