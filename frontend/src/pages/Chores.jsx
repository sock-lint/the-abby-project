import { useMemo, useState } from 'react';
import useSearchParamState from '../hooks/useSearchParamState';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Check, Plus, Pencil, Trash2,
  DollarSign, CalendarDays, RefreshCw,
} from 'lucide-react';
import {
  getChores, createChore, updateChore, deleteChore, completeChore,
  getChoreCompletions, approveChoreCompletion, rejectChoreCompletion,
  withdrawChoreCompletion,
  listMyChoreProposals, approveChoreProposal,
  getSkills,
} from '../api';
import { useApi } from '../hooks/useApi';
import useMountedRef from '../hooks/useMountedRef';
import { useFormState } from '../hooks/useFormState';
import useChildContext from '../hooks/useChildContext';
import ChildContext from '../components/family/ChildContext';
import { getFamilyChores, getFamilyChoreProposals, getFamilyChoreCompletions } from '../api';
import ApprovalQueue from '../components/ApprovalQueue';
import SubmissionTiming from '../components/SubmissionTiming';
import ReviewedWorkHistory from '../components/ReviewedWorkHistory';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import FilteredEmptyState from '../components/FilteredEmptyState';
import CatalogSearch from '../components/CatalogSearch';
import BottomSheet from '../components/BottomSheet';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import SkillTagEditor from '../components/SkillTagEditor';
import ChapterRubric from '../components/atlas/ChapterRubric';
import { CoinIcon, ScrollIcon } from '../components/icons/JournalIcons';
import { formatDate } from '../utils/format';
import { hapticTap } from '../utils/haptics';
import { normalizeList } from '../utils/api';
import Button from '../components/Button';
import IconButton from '../components/IconButton';
import ModalActions from '../components/ModalActions';
import AddToCalendar from '../components/AddToCalendar';
import { TextField, SelectField, TextAreaField, CheckboxField, IconPicker } from '../components/form';
import QuestFolio from './quests/QuestFolio';
import { choreReminderEvent, validateChoreReminderDate, nextChoreReminderDate } from './choresCalendar';

const RECURRENCE_LABELS = { daily: 'Daily', weekly: 'Weekly', one_time: 'One-time' };
const WEEK_SCHEDULE_LABELS = { every_week: 'Every week', alternating: 'Alternating weeks' };

// Mirrors the canonical STATUS_COLORS map in constants/colors.js, which
// StatusBadge renders on the sibling Study tab: waiting-on-a-parent is gold,
// the ember/error tone is reserved for rejected. Pending used to share ember
// with rejected, so the two states were indistinguishable by colour between
// two adjacent tabs of the same Quests hub.
const STATUS_TONE = {
  approved: 'moss',
  pending: 'gold',
  rejected: 'ember',
};

function ChoreFormModal({ chore, children, skills, isParent, initialChildId, mode, onClose, onSaved }) {
  // mode: 'create' | 'edit' | 'approve'. Resolved by caller so labels + submit
  // routing are unambiguous (approve has its own endpoint).
  const mounted = useMountedRef();
  const resolvedMode = mode || (chore ? 'edit' : 'create');
  const isApprove = resolvedMode === 'approve';
  const isEdit = resolvedMode === 'edit';
  const canSetRewards = isParent;
  const [advanced, setAdvanced] = useState(resolvedMode !== 'create');
  const [offerReward, setOfferReward] = useState(Number(chore?.reward_amount) > 0 || Number(chore?.coin_reward) > 0);

  const { form, set, saving, setSaving, error, setError, dirty } = useFormState({
    title: chore?.title || '',
    description: chore?.description || '',
    icon: chore?.icon || '',
    reward_amount: chore?.reward_amount ?? '1.00',
    coin_reward: chore?.coin_reward ?? 2,
    xp_reward: chore?.xp_reward ?? 10,
    recurrence: chore?.recurrence || 'daily',
    due_date: chore?.due_date || '',
    week_schedule: chore?.week_schedule || 'every_week',
    schedule_start_date: chore?.schedule_start_date || '',
    assigned_to: chore ? chore.assigned_to ?? '' : initialChildId ?? '',
    is_active: chore?.is_active ?? true,
    order: chore?.order ?? 0,
    skill_tags: (chore?.skill_tags || []).map((t) => ({
      skill_id: t.skill,
      xp_weight: t.xp_weight,
    })),
  });

  const onField = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    set({ [k]: val, ...(k === 'recurrence' && val !== 'one_time' ? { due_date: '' } : {}) });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isParent && form.assigned_to && !children.some((child) => String(child.id) === String(form.assigned_to))) {
      setError('Choose a child from your family or All children.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const base = {
        title: form.title,
        description: form.description,
        icon: form.icon,
        recurrence: form.recurrence,
        due_date: form.recurrence === 'one_time' ? form.due_date || null : null,
        week_schedule: form.recurrence === 'one_time' ? 'every_week' : form.week_schedule,
        schedule_start_date: form.week_schedule === 'alternating' && form.recurrence !== 'one_time'
          ? form.schedule_start_date || null : null,
      };
      const parentExtras = canSetRewards ? {
        reward_amount: offerReward ? form.reward_amount : '0.00',
        coin_reward: offerReward ? parseInt(form.coin_reward) || 0 : 0,
        xp_reward: parseInt(form.xp_reward) || 0,
        assigned_to: form.assigned_to ? parseInt(form.assigned_to) : null,
        is_active: form.is_active,
        order: parseInt(form.order) || 0,
        skill_tags: form.skill_tags,
      } : {};
      const payload = { ...base, ...parentExtras };

      if (isApprove) {
        await approveChoreProposal(chore.id, payload);
      } else if (isEdit) {
        await updateChore(chore.id, payload);
      } else {
        await createChore(payload);
      }
      if (!mounted.current) return;
      onSaved(isParent ? form.assigned_to : undefined);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const schedulePreview = form.week_schedule === 'alternating' && form.schedule_start_date
    ? nextChoreReminderDate(form) : null;
  const showSchedule = form.recurrence !== 'one_time';
  const title = isApprove
    ? 'Approve chore proposal'
    : isEdit
      ? 'Edit chore'
      : isParent ? 'New chore' : 'Propose a chore';
  const submitLabel = isApprove ? 'Approve & publish'
    : isEdit ? 'Update'
    : isParent ? 'Create' : 'Send to parent';

  return (
    <BottomSheet title={title} onClose={onClose} disabled={saving} dirty={dirty}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        {isApprove && chore?.created_by_name && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-body text-ink-primary">
            Proposed by <span className="font-body font-medium">{chore.created_by_name}</span>
            {' — set rewards below and publish to your chore list.'}
          </div>
        )}
        {!canSetRewards && !isApprove && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-body text-ink-primary">
            Your parent will set the rewards when they approve this.
          </div>
        )}
        <TextField label="Title" value={form.title} onChange={onField('title')} required />
        {isParent && <SelectField label="Assign to" value={form.assigned_to} onChange={onField('assigned_to')}>
          <option value="">All children</option>
          {children.map((child) => <option key={child.id} value={child.id}>{child.display_name || child.username}</option>)}
        </SelectField>}
        <SelectField label="Recurrence" value={form.recurrence} onChange={onField('recurrence')}>
          {Object.entries(RECURRENCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectField>
        {form.recurrence === 'one_time' && (
          <TextField label="Due date (optional)" type="date" value={form.due_date} onChange={onField('due_date')} helpText="Leave blank for no deadline." />
        )}
        {isParent && showSchedule && <>
          <SelectField label="Custody schedule" value={form.week_schedule} onChange={onField('week_schedule')}>
            {Object.entries(WEEK_SCHEDULE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </SelectField>
          {form.week_schedule === 'alternating' && <>
            <TextField label="Start date (on-week)" type="date" value={form.schedule_start_date} onChange={onField('schedule_start_date')} required />
            <p className="text-caption text-ink-secondary" role="status">{schedulePreview
              ? `Available in alternating weeks matching ${formatDate(form.schedule_start_date)}. Next available day: ${formatDate(schedulePreview)}.`
              : 'Choose any day in an on-week to preview the schedule.'}</p>
          </>}
        </>}
        {canSetRewards && <>
          <CheckboxField label="Offer money or coins (optional)" checked={offerReward} onChange={(event) => setOfferReward(event.target.checked)} />
          {offerReward && <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField label="Reward ($)" type="number" min="0" step="0.25" value={form.reward_amount} onChange={onField('reward_amount')} />
            <TextField label="Coins" type="number" min="0" value={form.coin_reward} onChange={onField('coin_reward')} />
          </div>}
          <Button variant="ghost" aria-expanded={advanced} onClick={() => setAdvanced((value) => !value)}>Advanced options</Button>
        </>}
        {(!isParent || advanced) && <div className="space-y-3">
          <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
          <IconPicker value={form.icon} onChange={(icon) => set({ icon })} placeholder="🧹" disabled={saving} />
          {canSetRewards && <>
            <TextField label="XP pool" type="number" min="0" value={form.xp_reward} onChange={onField('xp_reward')} />
            <TextField label="Order" type="number" value={form.order} onChange={onField('order')} />
            <CheckboxField label="Active" checked={form.is_active} onChange={onField('is_active')} />
            <SkillTagEditor skills={skills} value={form.skill_tags} onChange={(tags) => set({ skill_tags: tags })} />
          </>}
        </div>}
        <ModalActions
          onClose={onClose}
          submitLabel={submitLabel}
          saving={saving}
        />
      </form>
    </BottomSheet>
  );
}

export default function Chores() {
  const context = useChildContext();
  if (!context.user?.id || context.loading) return <Loader />;
  if (context.error) return <ErrorAlert message={context.error} onRetry={context.reload} />;
  return <ChoresWorkspace key={`${context.scope}:${context.targetUserId}`} context={context} />;
}

function ChoresWorkspace({ context }) {
  const mounted = useMountedRef();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isParent, children = [], targetUserId, selectedChild, selectChild } = context;

  const {
    data: choresData, loading: loadingChores, refreshing: refreshingChores, error: choresError, reload: reloadChores,
    setData: setChoresData,
  } = useApi(isParent ? getFamilyChores : getChores, [isParent]);
  const { data: completionsData, loading: loadingCompletions, refreshing: refreshingCompletions, error: completionsError, reload: reloadCompletions } = useApi(
    isParent ? getFamilyChoreCompletions : () => getChoreCompletions(),
    [isParent],
  );
  const { data: proposalsData, error: proposalsError, reload: reloadProposals } = useApi(
    isParent ? getFamilyChoreProposals : listMyChoreProposals,
    [isParent],
  );
  const { data: skillsData, error: skillsError, reload: reloadSkills } = useApi(isParent ? getSkills : () => Promise.resolve([]), [isParent]);

  const [proposeParam, setProposeParam] = useSearchParamState('propose', '');
  const [error, setError] = useState('');
  // The quick-actions FAB deep-links here with ?propose=1; without this the
  // row just landed on the tab and the kid had to find the button again.
  const [showForm, setShowForm] = useState(proposeParam === '1');
  const [editingChore, setEditingChore] = useState(null);
  const [formMode, setFormMode] = useState('create');
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [search, setSearch] = useState('');

  const loading = loadingChores && loadingCompletions;

  const choresList = useMemo(() => normalizeList(choresData).filter((chore) => !isParent
    || chore.assigned_to == null || String(chore.assigned_to) === String(targetUserId)), [choresData, isParent, targetUserId]);
  const filteredChores = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return choresList;
    return choresList.filter((c) => {
      const title = (c.title || '').toLowerCase();
      const desc = (c.description || '').toLowerCase();
      return title.includes(q) || desc.includes(q);
    });
  }, [choresList, search]);

  const refresh = () => {
    reloadChores();
    reloadCompletions();
    reloadProposals();
  };

  const handleComplete = async (choreId) => {
    // Same tap, same buzz as the dashboard's quick-complete (ChildDashboard).
    hapticTap();
    setError('');
    try {
      await completeChore(choreId);
      if (mounted.current) refresh();
    } catch (e) { setError(e.message); }
  };

  const handleApprove = async (id) => {
    try { await approveChoreCompletion(id); if (mounted.current) refresh(); }
    catch (e) { setError(e.message); }
  };

  const handleReject = async (id) => {
    try { await rejectChoreCompletion(id); if (mounted.current) refresh(); }
    catch (e) { setError(e.message); }
  };

  const handleWithdraw = async (completionId) => {
    if (!completionId) return;
    setError('');
    // Optimistic: flip the chore card back to actionable immediately so
    // the kid doesn't sit on a "pending" row waiting for the refetch.
    let snapshot = null;
    const patchChores = (prev, patch) => {
      if (!prev) return prev;
      const list = Array.isArray(prev) ? prev : prev.results || [];
      const idx = list.findIndex(
        (c) => c.today_completion_id === completionId
          || (snapshot && c.id === snapshot.id),
      );
      if (idx < 0) return prev;
      if (!snapshot) snapshot = list[idx];
      const updated = [...list];
      updated[idx] = patch(list[idx]);
      return Array.isArray(prev) ? updated : { ...prev, results: updated };
    };
    setChoresData((prev) =>
      patchChores(prev, (chore) => ({
        ...chore,
        today_status: null,
        today_completion_id: null,
      })),
    );
    try {
      await withdrawChoreCompletion(completionId);
      if (!mounted.current) return;
      refresh();
    } catch (e) {
      // Rollback to whatever the card looked like before the click.
      if (snapshot) {
        setChoresData((prev) => patchChores(prev, () => snapshot));
      }
      setError(e.message);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteChore(id);
      if (!mounted.current) return;
      setDeleteConfirm(null);
      refresh();
    } catch (e) { setError(e.message); }
  };

  if (loading) return <Loader />;

  const chores = choresList;
  const completions = normalizeList(completionsData).filter((completion) => !isParent || String(completion.user) === String(targetUserId));
  const proposals = normalizeList(proposalsData).filter((proposal) => !isParent || String(proposal.assigned_to ?? proposal.created_by) === String(targetUserId));
  const skills = normalizeList(skillsData);
  const pendingCompletions = completions.filter((c) => c.status === 'pending');

  const openCreate = () => {
    setEditingChore(null);
    setFormMode('create');
    setShowForm(true);
  };
  // Drop ?propose=1 as the sheet closes so a tab switch back here (ChapterHub
  // remounts tab bodies) doesn't re-open it.
  const closeForm = () => {
    setShowForm(false);
    setProposeParam('');
  };
  const handleSaved = (childId) => {
    if (isParent && String(childId) !== String(targetUserId) && children.some((child) => String(child.id) === String(childId))) {
      setShowForm(false);
      setEditingChore(null);
      const next = new URLSearchParams(searchParams);
      next.delete('propose');
      next.set('child', String(childId));
      setSearchParams(next, { replace: true });
    } else {
      closeForm();
      refresh();
    }
  };
  const openEdit = (chore) => {
    setEditingChore(chore);
    setFormMode('edit');
    setShowForm(true);
  };
  const openApprove = (chore) => {
    setEditingChore(chore);
    setFormMode('approve');
    setShowForm(true);
  };

  const doneCount = chores.filter(
    (c) => c.is_done || c.today_status === 'approved' || c.today_status === 'pending',
  ).length;
  const progressPct = chores.length > 0 ? Math.round((doneCount / chores.length) * 100) : 0;
  const versoStats = isParent
    ? [
      { value: completionsData === null ? '—' : pendingCompletions.length, label: 'awaiting approval' },
      { value: choresData === null ? '—' : chores.length, label: 'chores' },
    ]
    : [
      { value: choresData === null ? '—' : doneCount, label: 'done today' },
      { value: choresData === null ? '—' : chores.length, label: 'chores' },
    ];
  const versoProgressLabel = choresData === null ? 'Chores unavailable' : isParent
    ? `${chores.length} chores added`
    : (chores.length > 0
      ? `${doneCount} of ${chores.length} done today`
      : 'No chores today');

  // Track which rubric numeral comes next so empty sections don't burn
  // a §I that would otherwise look like a missing chapter.
  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="C"
        title="Chores"
        kicker="Help around the house"
        stats={versoStats}
        progressPct={progressPct}
        progressLabel={versoProgressLabel}
      >
        <ErrorAlert message={error} />
        <ErrorAlert message={choresError && `${choresData === null ? "Couldn't load chores." : "Couldn't update chores. Showing the last loaded list."} ${choresError}`} onRetry={reloadChores} />
        <ErrorAlert message={completionsError && `Couldn't load chore completions. ${completionsError}`} onRetry={reloadCompletions} />
        <ErrorAlert message={proposalsError && `Couldn't load chore proposals. ${proposalsError}`} onRetry={reloadProposals} />
        <ErrorAlert message={skillsError && `Couldn't load skills for chores. ${skillsError}`} onRetry={reloadSkills} />
        {(refreshingChores || refreshingCompletions) && <p role="status" className="text-caption text-ink-secondary">Updating chores and completions…</p>}
        {loadingCompletions && <p role="status" className="text-caption text-ink-secondary">Loading chore completions…</p>}

        {/* New / Propose action lives at the top of the recto so it stays
            reachable when the folio body is empty. */}
        {isParent && <ChildContext children={children} selectedChildId={targetUserId} onSelect={selectChild} />}
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={openCreate}
            className="flex items-center gap-1"
          >
            <Plus size={14} /> {isParent ? 'New chore' : 'Propose a chore'}
          </Button>
        </div>

        {/* Parent: pending approvals */}
        {isParent && pendingCompletions.length > 0 && (
          <section>
            <ChapterRubric index={nextRubric()} name="Awaiting approval" />
            <ApprovalQueue
              items={pendingCompletions}
              onApprove={handleApprove}
              onReject={handleReject}
            >
              {/* Stacked, not side-by-side: ApprovalButtons is ~220px of
                  labelled 44px targets, which left the kid-name + duty title
                  about 60px of column at 360px. Same shape as the Study tab's
                  pending-submission card. */}
              {({ item: c, actions }) => (
                <ParchmentCard key={c.id} className="space-y-3">
                  <div className="min-w-0">
                    <div className="font-body text-body font-medium text-ink-primary">
                      {c.user_name} — {c.chore_icon} {c.chore_title}
                    </div>
                    <SubmissionTiming record={c} kind="chore" />
                    <div className="font-script text-caption text-ink-whisper">
                      ${c.reward_amount_snapshot} + {c.coin_reward_snapshot} coins
                    </div>
                    {c.notes && (
                      <div className="font-script text-caption text-ink-secondary italic mt-0.5">
                        &ldquo;{c.notes}&rdquo;
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-end gap-1.5 flex-wrap">
                    {actions}
                  </div>
                </ParchmentCard>
              )}
            </ApprovalQueue>
          </section>
        )}

        {/* Pending proposals — parent reviews, child sees their own queue. */}
        {proposals.length > 0 && (
          <section>
            <ChapterRubric
              index={nextRubric()}
              name={isParent ? 'Chore proposals awaiting review' : 'Your proposals'}
              icon={<ScrollIcon size={18} className="text-gold-leaf" />}
            />
            <div className="space-y-2">
              {proposals.map((p) => (
                <ParchmentCard key={p.id} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-body text-body font-medium text-ink-primary flex items-center gap-2">
                      <span className="text-lg">{p.icon || '📋'}</span>
                      {p.title}
                      <RuneBadge tone="gold" size="sm">pending</RuneBadge>
                    </div>
                    <div className="font-script text-caption text-ink-whisper">
                      {isParent
                        ? `proposed by ${p.created_by_name || 'child'}`
                        : 'waiting for parent to set rewards'}
                    </div>
                  </div>
                  <div className="shrink-0 flex gap-1">
                    {isParent ? (
                      <>
                        <Button size="sm" onClick={() => openApprove(p)}>
                          Review &amp; publish
                        </Button>
                        <IconButton
                          variant="danger"
                          onClick={() => setDeleteConfirm(p.id)}
                          aria-label="Decline proposal"
                          className="min-w-[44px] min-h-[44px]"
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </>
                    ) : (
                      <RuneBadge tone="ink" size="sm">pending</RuneBadge>
                    )}
                  </div>
                </ParchmentCard>
              ))}
            </div>
          </section>
        )}

        {/* Chore list */}
        <section>
          <ChapterRubric
            index={nextRubric()}
            name={isParent ? 'All chores' : "Today's chores"}
            icon={<ScrollIcon size={18} className="text-sheikah-teal-deep" />}
          />
          {chores.length > 0 && (
            <div className="mb-3">
              <CatalogSearch
                value={search}
                onChange={setSearch}
                placeholder="Search chores…"
                ariaLabel="Filter chores"
              />
            </div>
          )}
          {loadingChores ? <Loader /> : choresData === null ? null : chores.length === 0 ? (
            <EmptyState icon={<ScrollIcon size={32} />}>
              {isParent
                ? 'No chores yet. Add one to get started.'
                : 'No chores available today.'}
            </EmptyState>
          ) : filteredChores.length === 0 ? (
            <FilteredEmptyState query={search.trim()} onClear={() => setSearch('')} icon={<ScrollIcon size={32} />} />
          ) : (
            <div className="space-y-2">
              {filteredChores.map((chore) => {
              const isDone = !isParent && (chore.today_status === 'approved' || chore.today_status === 'pending');
              const isAvailable = !isParent && chore.is_available;
              const isRejected = !isParent && chore.today_status === 'rejected';
              const calendarEvent = choreReminderEvent(chore);
              return (
                <ParchmentCard
                  key={chore.id}
                  className={`space-y-2 ${isDone ? 'opacity-60' : ''}`}
                >
                  <div className="flex items-center gap-3">
                    <div className="text-2xl shrink-0 w-10 text-center">{chore.icon || '📋'}</div>
                    <div className="flex-1 min-w-0">
                      <div className="font-body text-body font-medium text-ink-primary flex items-center gap-2">
                        {chore.title}
                        {isParent && !chore.is_active && (
                          <RuneBadge tone="ink" size="sm">inactive</RuneBadge>
                        )}
                      </div>
                      {chore.description && (
                        <div className="font-body text-caption text-ink-secondary line-clamp-1">
                          {chore.description}
                        </div>
                      )}
                      {/* Up to five chips ($, coins, recurrence, alt. weeks,
                          assignee) in a text column the parent view squeezes to
                          ~130px at 360px — wraps like its Study and Forge
                          siblings instead of painting past the card edge. */}
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 font-script text-caption text-ink-whisper">
                        <span className="flex items-center gap-0.5">
                          <DollarSign size={10} />{chore.reward_amount}
                        </span>
                        <span className="flex items-center gap-0.5">
                          <CoinIcon size={10} />{chore.coin_reward}
                        </span>
                        <span className="flex items-center gap-0.5">
                          <RefreshCw size={10} />{RECURRENCE_LABELS[chore.recurrence]}
                        </span>
                        {chore.recurrence === 'one_time' && chore.due_date && (
                          <span>Due {formatDate(chore.due_date)}</span>
                        )}
                        {chore.week_schedule === 'alternating' && (
                          <span className="flex items-center gap-0.5 text-royal">
                            <CalendarDays size={10} />alt. weeks
                          </span>
                        )}
                        {isParent && <span>{chore.assigned_to == null ? 'All children' : `For ${chore.assigned_to_name || selectedChild?.display_name || selectedChild?.username}`}</span>}
                      </div>
                    </div>
                    <div className="shrink-0">
                      {isParent ? (
                        <div className="flex gap-1">
                          <IconButton
                            variant="secondary"
                            onClick={() => openEdit(chore)}
                            aria-label="Edit chore"
                            className="min-w-[44px] min-h-[44px]"
                          >
                            <Pencil size={16} />
                          </IconButton>
                          <IconButton
                            variant="danger"
                            onClick={() => setDeleteConfirm(chore.id)}
                            aria-label="Delete chore"
                            className="min-w-[44px] min-h-[44px]"
                          >
                            <Trash2 size={16} />
                          </IconButton>
                        </div>
                      ) : isDone ? (
                        <div className="flex items-center gap-2">
                          <RuneBadge tone={STATUS_TONE[chore.today_status] || 'ink'} size="sm">
                            {chore.today_status}
                          </RuneBadge>
                          {chore.today_status === 'pending' && chore.today_completion_id && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleWithdraw(chore.today_completion_id)}
                              aria-label="Withdraw this chore submission"
                              title="Withdraw — pulls it out of the queue so you can re-do it"
                              className="font-script text-tiny hover:text-ember-deep underline-offset-2 hover:underline"
                            >
                              ↩ withdraw
                            </Button>
                          )}
                        </div>
                      ) : isRejected ? (
                        <Button
                          size="sm"
                          onClick={() => handleComplete(chore.id)}
                          className="flex items-center gap-1 text-caption"
                        >
                          <RefreshCw size={12} /> Retry
                        </Button>
                      ) : isAvailable ? (
                        <Button
                          size="sm"
                          onClick={() => handleComplete(chore.id)}
                          className="flex items-center gap-1 text-caption"
                        >
                          <Check size={14} /> Done
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  {calendarEvent && (
                    <div className="flex justify-end">
                      <AddToCalendar
                        event={calendarEvent}
                        dateEditable
                        dateHelp="Choose one day for this chore reminder. Repeat reminders can be set in your calendar."
                        validateDate={(date) => validateChoreReminderDate(chore, date)}
                      />
                    </div>
                  )}
                </ParchmentCard>
              );
            })}
          </div>
        )}
      </section>

        {isParent && targetUserId && <ReviewedWorkHistory kind="chore" childId={targetUserId} />}

        {/* Child: recent history */}
        {!isParent && completions.length > 0 && (
          <section>
            <ChapterRubric index={nextRubric()} name="Recent history" />
            <div className="space-y-2">
              {completions.slice(0, 10).map((c) => (
                <ParchmentCard key={c.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-lg">{c.chore_icon || '📋'}</span>
                    <div className="min-w-0">
                      <div className="font-body text-body font-medium text-ink-primary truncate">
                        {c.chore_title}
                      </div>
                      <SubmissionTiming record={c} kind="chore" />
                      <div className="font-script text-caption text-ink-whisper">
                        ${c.reward_amount_snapshot} + {c.coin_reward_snapshot} coins
                      </div>
                    </div>
                  </div>
                  <RuneBadge tone={STATUS_TONE[c.status] || 'ink'} size="sm">
                    {c.status}
                  </RuneBadge>
                </ParchmentCard>
              ))}
            </div>
          </section>
        )}
      </QuestFolio>

      {showForm && (
        <ChoreFormModal
          chore={editingChore}
          initialChildId={isParent ? targetUserId : undefined}
          children={children}
          skills={skills}
          isParent={isParent}
          mode={formMode}
          onClose={closeForm}
          onSaved={handleSaved}
        />
      )}

      {deleteConfirm && (
        <ConfirmDialog
          title="Delete chore?"
          message="This will also remove all completion history for this chore."
          onConfirm={() => handleDelete(deleteConfirm)}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}
    </div>
  );
}
