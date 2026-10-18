import { useState, useEffect, useRef } from 'react';
import { usePulse } from '../providers/pulseContext';

/**
 * Emits a toast for any new drop since last seen. Reads the shared heartbeat
 * (PulseProvider) rather than running its own timer — the diffing below is
 * unchanged, only the transport moved.
 *
 * Returns { toasts, dismiss } — toasts is an array of
 * {id, item_name, item_icon, item_rarity, was_salvaged}.
 */
export function useDropToasts() {
  const { pulse } = usePulse();
  const [toasts, setToasts] = useState([]);
  const seenIdsRef = useRef(new Set());
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!pulse) return;
    const list = Array.isArray(pulse.recent_drops) ? pulse.recent_drops : [];

    if (!initializedRef.current) {
      // First beat: seed seen IDs without showing toasts, so a page load
      // doesn't replay the last ten drops.
      for (const d of list) seenIdsRef.current.add(d.id);
      initializedRef.current = true;
      return;
    }

    const newDrops = list.filter((d) => !seenIdsRef.current.has(d.id));
    for (const d of newDrops) seenIdsRef.current.add(d.id);

    if (newDrops.length > 0) {
      setToasts((prev) => [...prev, ...newDrops.map((d) => ({
        id: d.id,
        item_name: d.item_name,
        item_icon: d.item_icon,
        item_sprite_key: d.item_sprite_key,
        item_catalog_icon: d.item_catalog_icon,
        item_rarity: d.item_rarity,
        item_type: d.item_type,
        item_description: d.item_description,
        item_metadata: d.item_metadata,
        item_effect_summary: d.item_effect_summary,
        item_catalog_available: d.item_catalog_available,
        was_salvaged: d.was_salvaged,
        salvage_coins: d.salvage_coins,
      }))]);
    }
  }, [pulse]);

  const dismiss = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return { toasts, dismiss };
}
