import { useState, useEffect, useRef } from 'react';
import { getRecentDrops } from '../api';

/**
 * Polls recent drops and emits a toast for any new drop since last seen.
 * Returns { toasts, dismiss } — toasts is an array of {id, item_name, item_icon, item_rarity, was_salvaged}.
 */
export function useDropToasts(pollIntervalMs = 20000) {
  const [toasts, setToasts] = useState([]);
  const seenIdsRef = useRef(new Set());
  const initializedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const drops = await getRecentDrops();
        const list = Array.isArray(drops) ? drops : (drops?.results || []);
        if (cancelled) return;

        if (!initializedRef.current) {
          // First poll: seed seen IDs without showing toasts
          for (const d of list) seenIdsRef.current.add(d.id);
          initializedRef.current = true;
          return;
        }

        // Find new drops
        const newDrops = list.filter(d => !seenIdsRef.current.has(d.id));
        for (const d of newDrops) seenIdsRef.current.add(d.id);

        if (newDrops.length > 0) {
          setToasts(prev => [...prev, ...newDrops.map(d => ({
            id: d.id,
            item_name: d.item_name,
            item_icon: d.item_icon,
            item_rarity: d.item_rarity,
            was_salvaged: d.was_salvaged,
          }))]);
        }
      } catch (e) {
        // silent fail — don't break the app for a poll
      }
    };

    poll();
    const interval = setInterval(poll, pollIntervalMs);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pollIntervalMs]);

  const dismiss = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  return { toasts, dismiss };
}
