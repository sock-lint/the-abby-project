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
      // Audit L6: skip polls while the tab is hidden. Burning a request
      // every 20s on a backgrounded tab is wasted server work for every
      // inactive user; on a slow network those queued GETs can also pile
      // up and 401-cascade on token rotation. The visibilitychange
      // handler below kicks an immediate poll on tab focus so a
      // backgrounded tab catches up the moment it returns.
      if (typeof document !== 'undefined' && document.hidden) return;
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
            item_sprite_key: d.item_sprite_key,
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

    // Catch up immediately when the tab becomes visible again so a user
    // returning to a long-backgrounded tab sees fresh drops without
    // waiting up to ``pollIntervalMs``.
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
  }, [pollIntervalMs]);

  const dismiss = (id) => setToasts(prev => prev.filter(t => t.id !== id));

  return { toasts, dismiss };
}
