import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ParentReviewContext } from '../providers/parentReviewContext';
import { getToken } from '../api/client';
import {
  getChoreCompletions, getHomeworkDashboard, getPendingRedemptions, getDashboard,
  listPendingCreations, listPendingChoreProposals, listPendingHabitProposals,
  getPendingExchangeRequests, getAllApprovalPages, listPrintRequests, getAwaitingRedemptions,
} from '../api';
import { normalizeList } from '../utils/api';
import { callWithDeferredRecovery } from './useApi';

function unifyChore(c) {
  return {
    id: c.id,
    kind: 'chore',
    kidId: c.user ?? c.user_id ?? null,
    kidName: c.user_name || c.user_display_name || 'Unassigned',
    title: c.chore_title || 'Chore',
    subtitle: c.notes || null,
    notes: c.notes || null,
    reward: c.reward_amount_snapshot ?? null,
    submittedAt: c.timing_snapshot?.submitted_at || c.submitted_at || c.created_at || null,
    timingRecord: c,
  };
}

function unifyHomework(h) {
  return {
    id: h.id,
    kind: 'homework',
    kidId: h.user_id ?? h.user ?? null,
    kidName: h.user_name || 'Unassigned',
    title: h.assignment_title || h.title || 'Homework',
    subtitle: null,
    reward: h.reward_amount_snapshot ?? null,
    submittedAt: h.timing_snapshot?.submitted_at || h.submitted_at || h.created_at || null,
    timingRecord: h,
    // The kid's evidence — carried through so a parent can judge the work
    // from the queue instead of hopping to Quests → Study to see it.
    notes: h.notes || null,
    proofs: normalizeList(h.proofs),
    proof_url: h.proof_url || '',
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

function unifyChoreProposal(c) {
  return {
    id: c.id,
    kind: 'chore_proposal',
    kidId: c.created_by ?? null,
    kidName: c.created_by_name || 'Child',
    title: c.title || 'Chore',
    subtitle: 'proposed — parent must set rewards',
    reward: null,
    submittedAt: c.updated_at || c.created_at || null,
  };
}

function unifyHabitProposal(h) {
  return {
    id: h.id,
    kind: 'habit_proposal',
    kidId: h.created_by ?? null,
    kidName: h.created_by_name || 'Child',
    title: h.name || 'Habit',
    subtitle: 'proposed — parent must set XP',
    reward: null,
    submittedAt: h.updated_at || h.created_at || null,
  };
}

function unifyRedemption(r) {
  return {
    id: r.id,
    kind: 'redemption',
    kidId: r.user_id ?? r.user ?? null,
    kidName: r.user_name || 'Unassigned',
    title: r.reward?.name || 'Reward',
    subtitle: r.coin_cost_snapshot != null ? `${r.coin_cost_snapshot} coins` : null,
    reward: null,
    submittedAt: r.requested_at || r.created_at || null,
    coinCost: r.coin_cost_snapshot ?? null,
    fulfillmentKind: r.fulfillment_kind_snapshot || r.reward?.fulfillment_kind || 'real_world',
  };
}

function unifyExchange(e) {
  const dollars = Number(e.dollar_amount);
  const coins = Number(e.coin_amount);
  return {
    id: e.id,
    kind: 'exchange',
    kidId: e.user ?? e.user_id ?? null,
    kidName: e.user_name || 'Unassigned',
    title: Number.isFinite(dollars) ? `Exchange $${dollars.toFixed(2)} → coins` : 'Exchange request',
    subtitle: Number.isFinite(coins) ? `${coins} coins at the current rate` : null,
    reward: null,
    submittedAt: e.created_at || null,
  };
}

function byRecent(a, b) {
  const ta = a.submittedAt ? new Date(a.submittedAt).getTime() : 0;
  const tb = b.submittedAt ? new Date(b.submittedAt).getTime() : 0;
  return tb - ta;
}

// Each fetch in load() is paired with a label here; failures get reported
// up to the dashboard so a 500 doesn't silently disappear from the queue.
const SOURCES = [
  { key: 'chores',         label: 'chore approvals',      fn: () => getAllApprovalPages(() => getChoreCompletions('pending', { space: 'family' })), fallback: [] },
  { key: 'homework',       label: 'homework approvals',   fn: () => getHomeworkDashboard(),          fallback: { pending_submissions: [] } },
  { key: 'redemptions',    label: 'reward redemptions',   fn: getPendingRedemptions,                 fallback: [] },
  { key: 'dashboard',      label: 'week summary',         fn: (signal) => callWithDeferredRecovery((requestSignal) => getDashboard(requestSignal, { space: 'family' }), signal), withSignal: true, fallback: null },
  { key: 'creations',      label: 'creation bonuses',     fn: () => getAllApprovalPages(listPendingCreations),      fallback: [] },
  { key: 'choreProposals', label: 'chore proposals',      fn: () => getAllApprovalPages(listPendingChoreProposals), fallback: [] },
  { key: 'habitProposals', label: 'habit proposals',      fn: () => getAllApprovalPages(listPendingHabitProposals), fallback: [] },
  { key: 'exchanges',      label: 'coin exchanges',       fn: getPendingExchangeRequests,            fallback: [] },
  { key: 'deliveries', label: 'reward deliveries', fn: getAwaitingRedemptions, fallback: [] },
  { key: 'prints',         label: 'print approvals',      fn: () => getAllApprovalPages(() => listPrintRequests({ status: 'pending' }, { space: 'family' })), fallback: [] },
];

/**
 * useParentDashboard — aggregates pending approvals across chores, homework,
 * and redemptions plus per-kid week stats. Returns a unified `pending` array
 * sorted newest-first, plus `failedSources` (string labels) for any fetch
 * that errored so the caller can surface the failure instead of silently
 * dropping rows from the queue. Prints need slicer estimates and a reviewed
 * quote, so `pendingPrintCount` is separate from inline/bulk approval rows.
 */
export const EMPTY_PARENT_REVIEW = {
  pending: [], pendingPrintCount: 0, pendingDeliveryCount: 0, deliveries: [],
  weekByKid: [], dashboard: null, loading: true, error: null, failedSources: [],
  attentionCount: 0,
};

export function useParentDashboardData({ enabled = true, accountScope } = {}) {
  const token = getToken();
  const scope = accountScope ?? token;
  const [saved, setSaved] = useState(null);
  const sequence = useRef(0);
  const mounted = useRef(false);
  const controllerRef = useRef(null);
  const data = saved?.scope === scope ? saved.data : EMPTY_PARENT_REVIEW;

  const load = useCallback(async () => {
    if (!enabled) return;
    const request = ++sequence.current;
    // A newer load or an unmount cancels the deferred-recovery wait, so a
    // superseded review neither re-fetches nor reports.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const current = () => mounted.current && sequence.current === request && getToken() === token;
    setSaved((previous) => ({ scope, data: { ...(previous?.scope === scope ? previous.data : EMPTY_PARENT_REVIEW), loading: true, error: null } }));
    const settled = await Promise.allSettled(SOURCES.map((source) => source.fn(source.withSignal ? controller.signal : undefined)));
    if (!current()) return;
    const failedSources = [];
    const values = {};
    settled.forEach((result, index) => {
      const source = SOURCES[index];
      if (result.status === 'fulfilled') values[source.key] = result.value;
      else { values[source.key] = source.fallback; failedSources.push(source.label); }
    });
    const { chores, homework: hw, redemptions: reds, dashboard: dashboardRes,
      creations, choreProposals, habitProposals, exchanges, prints, deliveries } = values;
    const pending = [
      ...normalizeList(chores).map(unifyChore),
      ...normalizeList(hw?.pending_submissions).map(unifyHomework),
      ...normalizeList(reds).filter((row) => row.status === 'pending').map(unifyRedemption),
      ...normalizeList(creations).map(unifyCreation),
      ...normalizeList(choreProposals).map(unifyChoreProposal),
      ...normalizeList(habitProposals).map(unifyHabitProposal),
      ...normalizeList(exchanges).filter((row) => row.status === 'pending').map(unifyExchange),
    ].sort(byRecent);
    const pendingPrintCount = normalizeList(prints).filter((row) => row.status === 'pending').length;
    const awaiting = normalizeList(deliveries).filter((row) => row.status === 'approved'
      && ['real_world', 'both'].includes(row.fulfillment_kind_snapshot || row.reward?.fulfillment_kind));
    const timecards = (Number(dashboardRes?.pending_timecards) || 0) + (Number(dashboardRes?.disputed_timecards) || 0);
    setSaved({ scope, data: {
      pending, pendingPrintCount, pendingDeliveryCount: awaiting.length, deliveries: awaiting,
      weekByKid: dashboardRes?.this_week_by_kid ?? [], dashboard: dashboardRes,
      loading: false, error: null, failedSources,
      attentionCount: pending.length + pendingPrintCount + awaiting.length + timecards,
    } });
  }, [enabled, scope, token]);

  useEffect(() => {
    mounted.current = true;
    const initialSequence = sequence.current;
    void Promise.resolve().then(() => { if (mounted.current && sequence.current === initialSequence) return load(); });
    return () => { mounted.current = false; sequence.current += 1; controllerRef.current?.abort(); };
  }, [load]);
  return { ...data, reload: load };
}

export default function useParentDashboard({ enabled = true } = {}) {
  const shared = useContext(ParentReviewContext);
  const local = useParentDashboardData({ enabled: enabled && shared === null });
  return shared ? { ...shared, isShared: true } : local;
}
