import { useCallback, useEffect, useState } from 'react';
import {
  getChoreCompletions, getHomeworkDashboard, getRedemptions, getDashboard,
  listPendingCreations,
} from '../api';
import { normalizeList } from '../utils/api';

function unifyChore(c) {
  return {
    id: c.id,
    kind: 'chore',
    kidId: c.user ?? c.user_id ?? null,
    kidName: c.user_name || c.user_display_name || 'Unassigned',
    title: c.chore_title || 'Duty',
    subtitle: c.notes || null,
    reward: c.reward_amount_snapshot ?? null,
    submittedAt: c.submitted_at || c.created_at || null,
  };
}

function unifyHomework(h) {
  return {
    id: h.id,
    kind: 'homework',
    kidId: h.user_id ?? h.user ?? null,
    kidName: h.user_name || 'Unassigned',
    title: h.assignment_title || h.title || 'Study',
    subtitle: h.timeliness ? `submitted ${h.timeliness}` : null,
    reward: h.reward_amount_snapshot ?? null,
    submittedAt: h.submitted_at || h.created_at || null,
  };
}

function unifyCreation(c) {
  return {
    id: c.id,
    kind: 'creation',
    kidId: c.user ?? c.user_id ?? null,
    kidName: c.user_display || 'Unassigned',
    title: c.caption || `${c.primary_skill_name || 'Creation'}`,
    subtitle: c.primary_skill_name
      ? `${c.primary_skill_category || ''} · ${c.primary_skill_name}`.trim()
      : null,
    reward: null,
    submittedAt: c.updated_at || c.created_at || null,
    image: c.image || null,
  };
}

function unifyRedemption(r) {
  return {
    id: r.id,
    kind: 'redemption',
    kidId: r.user_id ?? r.user ?? null,
    kidName: r.user_name || 'Unassigned',
    title: r.reward_name || 'Reward',
    subtitle: r.cost_coins != null ? `${r.cost_coins} coins` : null,
    reward: null,
    submittedAt: r.created_at || null,
  };
}

function byRecent(a, b) {
  const ta = a.submittedAt ? new Date(a.submittedAt).getTime() : 0;
  const tb = b.submittedAt ? new Date(b.submittedAt).getTime() : 0;
  return tb - ta;
}

/**
 * useParentDashboard — aggregates pending approvals across chores, homework,
 * and redemptions plus per-kid week stats. Returns a unified `pending` array
 * sorted newest-first.
 */
export default function useParentDashboard() {
  const [data, setData] = useState({
    pending: [],
    weekByKid: [],
    dashboard: null,
    loading: true,
    error: null,
  });

  const load = useCallback(async () => {
    setData((d) => ({ ...d, loading: true, error: null }));
    try {
      const [chores, hw, reds, dashboardRes, creations] = await Promise.all([
        getChoreCompletions('pending').catch(() => []),
        getHomeworkDashboard().catch(() => ({ pending_submissions: [] })),
        getRedemptions().catch(() => []),
        getDashboard().catch(() => null),
        listPendingCreations().catch(() => []),
      ]);

      const unified = [
        ...normalizeList(chores).map(unifyChore),
        ...normalizeList(hw?.pending_submissions).map(unifyHomework),
        ...normalizeList(reds).filter((r) => r.status === 'pending').map(unifyRedemption),
        ...normalizeList(creations).map(unifyCreation),
      ].sort(byRecent);

      // Week stats — if the dashboard payload has per-kid data in the future,
      // use it; otherwise leave the list empty and the UI hides the block.
      const weekByKid = dashboardRes?.this_week_by_kid ?? [];

      setData({
        pending: unified,
        weekByKid,
        dashboard: dashboardRes,
        loading: false,
        error: null,
      });
    } catch (err) {
      setData((d) => ({ ...d, loading: false, error: err?.message || 'Could not load.' }));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { ...data, reload: load };
}
