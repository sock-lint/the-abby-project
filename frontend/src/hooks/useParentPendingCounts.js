import { useEffect, useState } from 'react';

import { getChoreCompletions, getHomeworkDashboard, getRedemptions } from '../api';
import { normalizeList } from '../utils/api';

/**
 * Returns pending-approval counts for a parent user across the three
 * surfaces every parent sees: chore completions, homework submissions,
 * and reward redemptions. Used by both ``HeaderStatusPips`` (which only
 * needs the total) and ``useParentDashboard`` (which builds the full
 * unified queue) so both fetch the same data once each on mount.
 *
 * Skips the fetch when ``enabled`` is false (e.g. when called from a
 * child user's session) so a child never makes parent-only API calls.
 *
 * Failures are swallowed per-source: one endpoint hiccup shouldn't
 * blank out the whole pip strip.
 */
export default function useParentPendingCounts({ enabled = true } = {}) {
  const [counts, setCounts] = useState({
    chores: 0,
    homework: 0,
    redemptions: 0,
    total: 0,
    ready: false,
  });

  useEffect(() => {
    if (!enabled) {
      setCounts((c) => ({ ...c, ready: true }));
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const [chores, hw, reds] = await Promise.all([
          getChoreCompletions('pending').catch(() => []),
          getHomeworkDashboard().catch(() => ({ pending_submissions: [] })),
          getRedemptions().catch(() => []),
        ]);
        if (cancelled) return;
        const c = normalizeList(chores).length;
        const h = normalizeList(hw?.pending_submissions).length;
        const r = normalizeList(reds).filter((x) => x.status === 'pending').length;
        setCounts({
          chores: c,
          homework: h,
          redemptions: r,
          total: c + h + r,
          ready: true,
        });
      } catch {
        if (!cancelled) {
          setCounts({
            chores: 0, homework: 0, redemptions: 0, total: 0, ready: true,
          });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [enabled]);

  return counts;
}
