import { useCallback, useEffect, useRef, useState } from 'react';
import { getLorebook, updateMe } from '../api';
import { usePulse } from '../providers/pulseContext';
import { useAuth } from './useApi';

function normalizeEntries(response) {
  const list = Array.isArray(response?.entries) ? response.entries : [];
  return new Map(list.map((entry) => [entry.slug, entry]));
}

/**
 * Watches the shared heartbeat for newly unlocked Lorebook entries and
 * exposes a single active entry for the first-encounter sheet. Separate from
 * useDropToasts: drops are item celebrations, while Lorebook sheets teach a
 * newly discovered mechanic and must mark a per-user seen flag.
 */
export function useFirstEncounter() {
  const { user, setUser } = useAuth();
  const { pulse } = usePulse();
  const [activeEntry, setActiveEntry] = useState(null);
  const queuedRef = useRef([]);
  const entryMapRef = useRef(new Map());
  const dismissedThisSessionRef = useRef(new Set());
  const busyRef = useRef(false);

  useEffect(() => {
    if (!pulse) return;
    if (!user || user.role === 'parent') return;
    if (busyRef.current || activeEntry) return;

    const slugs = Array.isArray(pulse.newly_unlocked_lorebook)
      ? pulse.newly_unlocked_lorebook
      : [];
    if (slugs.length === 0) return;

    const flags = user?.lorebook_flags || {};
    const unseen = slugs.filter(
      (slug) => !dismissedThisSessionRef.current.has(slug) && !flags[`${slug}_seen`],
    );
    if (unseen.length === 0) return;

    queuedRef.current = unseen;
    const nextSlug = queuedRef.current.shift();

    // Lorebook copy is static content, so it is fetched once and only when a
    // sheet is actually about to show. The old hook re-fetched it — alongside
    // the entire dashboard — every 20 seconds just to check for slugs.
    let cancelled = false;
    const show = async () => {
      if (entryMapRef.current.size === 0) {
        try {
          entryMapRef.current = normalizeEntries(await getLorebook());
        } catch {
          // Fall through to the slug-only placeholder below.
        }
      }
      if (cancelled) return;
      setActiveEntry(
        entryMapRef.current.get(nextSlug) || { slug: nextSlug, title: nextSlug },
      );
    };
    show();
    return () => { cancelled = true; };
  }, [pulse, activeEntry, user]);

  const dismiss = useCallback(async () => {
    if (!activeEntry) return;
    const slug = activeEntry.slug;
    dismissedThisSessionRef.current.add(slug);
    busyRef.current = true;
    try {
      const nextUser = await updateMe({ lorebook_flags: { [`${slug}_seen`]: true } });
      setUser?.(nextUser);
    } finally {
      busyRef.current = false;
      setActiveEntry(null);
      const nextSlug = queuedRef.current.find((s) => !dismissedThisSessionRef.current.has(s));
      if (nextSlug) {
        queuedRef.current = queuedRef.current.filter((s) => s !== nextSlug);
        const nextEntry = entryMapRef.current.get(nextSlug) || { slug: nextSlug, title: nextSlug };
        if (nextEntry) setActiveEntry(nextEntry);
      }
    }
  }, [activeEntry, setUser]);

  return { activeEntry, dismiss };
}
