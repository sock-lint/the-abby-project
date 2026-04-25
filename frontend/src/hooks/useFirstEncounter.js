import { useCallback, useEffect, useRef, useState } from 'react';
import { getDashboard, getLorebook, updateMe } from '../api';
import { useAuth } from './useApi';

function normalizeEntries(response) {
  const list = Array.isArray(response?.entries) ? response.entries : [];
  return new Map(list.map((entry) => [entry.slug, entry]));
}

/**
 * Polls the dashboard for newly unlocked Lorebook entries and exposes a
 * single active entry for the first-encounter sheet. Separate from
 * useDropToasts: drops are item celebrations, while Lorebook sheets teach a
 * newly discovered mechanic and must mark a per-user seen flag.
 */
export function useFirstEncounter(pollIntervalMs = 20000) {
  const { user, setUser } = useAuth();
  const [activeEntry, setActiveEntry] = useState(null);
  const queuedRef = useRef([]);
  const entryMapRef = useRef(new Map());
  const dismissedThisSessionRef = useRef(new Set());
  const busyRef = useRef(false);

  useEffect(() => {
    if (!user || user.role === 'parent') return undefined;
    let cancelled = false;

    const poll = async () => {
      if (busyRef.current || activeEntry) return;
      try {
        const [dashboard, lorebook] = await Promise.all([getDashboard(), getLorebook()]);
        if (cancelled) return;
        entryMapRef.current = normalizeEntries(lorebook);
        const slugs = Array.isArray(dashboard?.newly_unlocked_lorebook)
          ? dashboard.newly_unlocked_lorebook
          : [];
        const flags = user?.lorebook_flags || {};
        const unseen = slugs.filter((slug) =>
          !dismissedThisSessionRef.current.has(slug) && !flags[`${slug}_seen`]);
        queuedRef.current = unseen;
        const nextSlug = queuedRef.current.shift();
        if (nextSlug) {
          const entry = entryMapRef.current.get(nextSlug) || { slug: nextSlug, title: nextSlug };
          if (entry) setActiveEntry(entry);
        }
      } catch {
        // Silent like drop polling — Lorebook teaching should never break the shell.
      }
    };

    poll();
    const id = setInterval(poll, pollIntervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeEntry, pollIntervalMs, user]);

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
