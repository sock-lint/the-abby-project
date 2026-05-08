import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Check, Plus, Pencil, Trash2,
  DollarSign, CalendarDays, RefreshCw,
} from 'lucide-react';
import {
  getChores, createChore, updateChore, deleteChore, completeChore,
  getChoreCompletions, approveChoreCompletion, rejectChoreCompletion,
  withdrawChoreCompletion,
  listMyChoreProposals, listPendingChoreProposals, approveChoreProposal,
  getChildren, getSkills,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useFormState } from '../hooks/useFormState';
import { useRole } from '../hooks/useRole';
import ApprovalQueue from '../components/ApprovalQueue';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import BottomSheet from '../components/BottomSheet';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import SkillTagEditor from '../components/SkillTagEditor';
import { CoinIcon, ScrollIcon } from '../components/icons/JournalIcons';
import { formatDate } from '../utils/format';
import { normalizeList } from '../utils/api';
import Button from '../components/Button';
import ModalActions from '../components/ModalActions';
import { TextField, SelectField, TextAreaField } from '../components/form';

const RECURRENCE_LABELS = { daily: 'Daily', weekly: 'Weekly', one_time: 'One-time' };
const WEEK_SCHEDULE_LABELS = { every_week: 'Every week', alternating: 'Alternating weeks' };

const STATUS_TONE = {
  approved: 'moss',
  pending: 'ember',
  rejected: 'ember',
};

function ChoreFormModal({ chore, children, skills, isParent, mode, onClose, onSaved }) {
  // mode: 'create' | 'edit' | 'approve'. Resolved by caller so labels + submit
  // routing are unambiguous (approve has its own endpoint).
  const resolvedMode = mode || (chore ? 'edit' : 'create');
  const isApprove = resolvedMode === 'approve';
  const isEdit = resolvedMode === 'edit';
  const canSetRewards = isParent;

  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: chore?.title || '',
    description: chore?.description || '',
    icon: chore?.icon || '',
    reward_amount: chore?.reward_amount ?? '1.00',
    coin_reward: chore?.coin_reward ?? 2,
    xp_reward: chore?.xp_reward ?? 10,
    recurrence: chore?.recurrence || 'daily',
    week_schedule: chore?.week_schedule || 'every_week',
    schedule_start_date: chore?.schedule_start_date || '',
    assigned_to: chore?.assigned_to ?? '',
    is_active: chore?.is_active ?? true,
    order: chore?.order ?? 0,
    skill_tags: (chore?.skill_tags || []).map((t) => ({
      skill_id: t.skill,
      xp_weight: t.xp_weight,
    })),
  });

  const onField = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    set({ [k]: val });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const base = {
        title: form.title,
        description: form.description,
        icon: form.icon,
        recurrence: form.recurrence,
        week_schedule: form.recurrence === 'one_time' ? 'every_week' : form.week_schedule,
        schedule_start_date: form.week_schedule === 'alternating' && form.recurrence !== 'one_time'
          ? form.schedule_start_date || null : null,
      };
      const parentExtras = canSetRewards ? {
        reward_amount: form.reward_amount,
        coin_reward: parseInt(form.coin_reward) || 0,
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
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const showSchedule = form.recurrence !== 'one_time';
  const title = isApprove
    ? 'Approve duty proposal'
    : isEdit
      ? 'Edit Duty'
      : isParent ? 'New Duty' : 'Propose a Duty';
  const submitLabel = isApprove ? 'Approve & publish'
    : isEdit ? 'Update'
    : isParent ? 'Create' : 'Send to parent';

  return (
    <BottomSheet title={title} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        {isApprove && chore?.created_by_name && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-sm text-ink-primary">
            Proposed by <span className="font-body font-medium">{chore.created_by_name}</span>
            {' — set rewards below and publish to your duty list.'}
          </div>
        )}
        {!canSetRewards && !isApprove && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-sm text-ink-primary">
            Your parent will set the rewards when they approve this.
          </div>
        )}
        <TextField label="Title" value={form.title} onChange={onField('title')} required />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Icon" value={form.icon} onChange={onField('icon')} placeholder="🧹" />
          <SelectField label="Recurrence" value={form.recurrence} onChange={onField('recurrence')}>
            {Object.entries(RECURRENCE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </SelectField>
        </div>
        {canSetRewards && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <TextField label="Reward ($)" type="number" min="0" step="0.25" value={form.reward_amount} onChange={onField('reward_amount')} />
              <TextField label="Coins" type="number" min="0" value={form.coin_reward} onChange={onField('coin_reward')} />
              <TextField label="XP pool" type="number" min="0" value={form.xp_reward} onChange={onField('xp_reward')} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <SelectField label="Assign to" value={form.assigned_to} onChange={onField('assigned_to')}>
                <option value="">All children</option>
                {children.map((c) => (
                  <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
                ))}
              </SelectField>
              <TextField label="Order" type="number" value={form.order} onChange={onField('order')} />
            </div>
            {showSchedule && (
              <div className="grid grid-cols-2 gap-3">
                <SelectField label="Custody schedule" value={form.week_schedule} onChange={onField('week_schedule')}>
                  {Object.entries(WEEK_SCHEDULE_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </SelectField>
                {form.week_schedule === 'alternating' && (
                  <TextField label="Start date (on-week)" type="date" value={form.schedule_start_date} onChange={onField('schedule_start_date')} />
                )}
              </div>
            )}
            <label className="flex items-center gap-2 font-body text-sm text-ink-primary">
              <input type="checkbox" checked={form.is_active} onChange={onField('is_active')} className="accent-sheikah-teal-deep" />
              Active
            </label>
            <SkillTagEditor
              skills={skills}
              value={form.skill_tags}
              onChange={(tags) => set({ skill_tags: tags })}
            />
          </>
        )}
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
  const { isParent } = useRole();

  const { data: choresData, loading: loadingChores, reload: reloadChores } = useApi(getChores);
  const { data: completionsData, loading: loadingCompletions, reload: reloadCompletions } = useApi(
    isParent ? () => getChoreCompletions('pending') : () => getChoreCompletions(),
    [isParent],
  );
  const { data: proposalsData, reload: reloadProposals } = useApi(
    isParent ? listPendingChoreProposals : listMyChoreProposals,
    [isParent],
  );
  const { data: childrenData } = useApi(isParent ? getChildren : () => Promise.resolve([]), [isParent]);
  const { data: skillsData } = useApi(isParent ? getSkills : () => Promise.resolve([]), [isParent]);

  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingChore, setEditingChore] = useState(null);
  const [formMode, setFormMode] = useState('create');
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const loading = loadingChores || loadingCompletions;

  const refresh = () => {
    reloadChores();
    reloadCompletions();
    reloadProposals();
  };

  const handleComplete = async (choreId) => {
    setError('');
    try {
      await completeChore(choreId);
      refresh();
    } catch (e) { setError(e.message); }
  };

  const handleApprove = async (id) => {
    try { await approveChoreCompletion(id); refresh(); }
    catch (e) { setError(e.message); }
  };

  const handleReject = async (id) => {
    try { await rejectChoreCompletion(id); refresh(); }
    catch (e) { setError(e.message); }
  };

  const handleWithdraw = async (completionId) => {
    if (!completionId) return;
    try { await withdrawChoreCompletion(completionId); refresh(); }
    catch (e) { setError(e.message); }
  };

  const handleDelete = async (id) => {
    try {
      await deleteChore(id);
      setDeleteConfirm(null);
      refresh();
    } catch (e) { setError(e.message); }
  };

  if (loading) return <Loader />;

  const chores = normalizeList(choresData);
  const completions = normalizeList(completionsData);
  const proposals = normalizeList(proposalsData);
  const children = normalizeList(childrenData);
  const skills = normalizeList(skillsData);
  const pendingCompletions = completions.filter((c) => c.status === 'pending');

  const openCreate = () => {
    setEditingChore(null);
    setFormMode('create');
    setShowForm(true);
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

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            duties · the daily keep
          </div>
          <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
            Daily duties
          </h2>
        </div>
        <Button
          size="sm"
          onClick={openCreate}
          className="flex items-center gap-1"
        >
          <Plus size={14} /> {isParent ? 'New duty' : 'Propose a duty'}
        </Button>
      </header>

      <ErrorAlert message={error} />

      {/* Child summary card */}
      {!isParent && chores.length > 0 && (
        <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
          <ParchmentCard flourish tone="bright" className="text-center py-6">
            <div className="font-script text-ink-whisper text-xs uppercase tracking-widest">
              today's progress
            </div>
            <div className="font-display font-semibold text-5xl tabular-nums text-sheikah-teal-deep mt-1">
              {doneCount}
              <span className="font-script text-2xl text-ink-whisper"> / {chores.length}</span>
            </div>
          </ParchmentCard>
        </motion.div>
      )}

      {/* Parent: pending approvals */}
      {isParent && (
        <ApprovalQueue
          items={pendingCompletions}
          title="Awaiting your seal"
          onApprove={handleApprove}
          onReject={handleReject}
        >
          {({ item: c, actions }) => (
            <ParchmentCard key={c.id} className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="font-body text-sm font-medium text-ink-primary">
                  {c.user_name} — {c.chore_icon} {c.chore_title}
                </div>
                <div className="font-script text-xs text-ink-whisper">
                  {formatDate(c.completed_date)} · ${c.reward_amount_snapshot} + {c.coin_reward_snapshot} coins
                </div>
                {c.notes && (
                  <div className="font-script text-xs text-ink-secondary italic mt-0.5">
                    &ldquo;{c.notes}&rdquo;
                  </div>
                )}
              </div>
              <div className="shrink-0">{actions}</div>
            </ParchmentCard>
          )}
        </ApprovalQueue>
      )}

      {/* Pending proposals — parent reviews, child sees their own queue. */}
      {proposals.length > 0 && (
        <section aria-labelledby="pending-proposals-heading">
          <div className="flex items-center gap-2 mb-3">
            <ScrollIcon size={18} className="text-gold-leaf" />
            <h2
              id="pending-proposals-heading"
              className="font-display text-xl text-ink-primary leading-tight"
            >
              {isParent ? 'Duty proposals awaiting review' : 'Your proposals'}
            </h2>
          </div>
          <div className="space-y-2">
            {proposals.map((p) => (
              <ParchmentCard key={p.id} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-body text-sm font-medium text-ink-primary flex items-center gap-2">
                    <span className="text-lg">{p.icon || '📋'}</span>
                    {p.title}
                    <RuneBadge tone="ember" size="sm">pending</RuneBadge>
                  </div>
                  <div className="font-script text-xs text-ink-whisper">
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
                      <button
                        type="button"
                        onClick={() => setDeleteConfirm(p.id)}
                        aria-label="Decline proposal"
                        className="p-1.5 bg-ink-page hover:bg-ember/25 rounded text-ink-secondary hover:text-ember-deep transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
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
        <div className="flex items-center gap-2 mb-3">
          <ScrollIcon size={18} className="text-sheikah-teal-deep" />
          <h2 className="font-display text-xl text-ink-primary leading-tight">
            {isParent ? 'All duties' : "Today's duties"}
          </h2>
        </div>
        {chores.length === 0 ? (
          <EmptyState icon={<ScrollIcon size={32} />}>
            {isParent
              ? 'No duties inscribed yet. Add one to begin the keep.'
              : 'No duties available today.'}
          </EmptyState>
        ) : (
          <div className="space-y-2">
            {chores.map((chore) => {
              const isDone = !isParent && (chore.today_status === 'approved' || chore.today_status === 'pending');
              const isAvailable = !isParent && chore.is_available;
              const isRejected = !isParent && chore.today_status === 'rejected';
              return (
                <ParchmentCard
                  key={chore.id}
                  className={`flex items-center gap-3 ${isDone ? 'opacity-60' : ''}`}
                >
                  <div className="text-2xl shrink-0 w-10 text-center">{chore.icon || '📋'}</div>
                  <div className="flex-1 min-w-0">
                    <div className="font-body text-sm font-medium text-ink-primary flex items-center gap-2">
                      {chore.title}
                      {isParent && !chore.is_active && (
                        <RuneBadge tone="ink" size="sm">inactive</RuneBadge>
                      )}
                    </div>
                    {chore.description && (
                      <div className="font-body text-xs text-ink-secondary line-clamp-1">
                        {chore.description}
                      </div>
                    )}
                    <div className="flex items-center gap-3 mt-1 font-script text-xs text-ink-whisper">
                      <span className="flex items-center gap-0.5">
                        <DollarSign size={10} />{chore.reward_amount}
                      </span>
                      <span className="flex items-center gap-0.5">
                        <CoinIcon size={10} />{chore.coin_reward}
                      </span>
                      <span className="flex items-center gap-0.5">
                        <RefreshCw size={10} />{RECURRENCE_LABELS[chore.recurrence]}
                      </span>
                      {chore.week_schedule === 'alternating' && (
                        <span className="flex items-center gap-0.5 text-royal">
                          <CalendarDays size={10} />alt. weeks
                        </span>
                      )}
                      {isParent && chore.assigned_to_name && (
                        <span>{chore.assigned_to_name}</span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0">
                    {isParent ? (
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(chore)}
                          aria-label="Edit duty"
                          className="p-1.5 bg-ink-page hover:bg-ink-page-shadow/70 rounded text-ink-secondary hover:text-ink-primary transition-colors"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteConfirm(chore.id)}
                          aria-label="Delete duty"
                          className="p-1.5 bg-ink-page hover:bg-ember/25 rounded text-ink-secondary hover:text-ember-deep transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ) : isDone ? (
                      <div className="flex items-center gap-2">
                        <RuneBadge tone={STATUS_TONE[chore.today_status] || 'ember'} size="sm">
                          {chore.today_status}
                        </RuneBadge>
                        {chore.today_status === 'pending' && chore.today_completion_id && (
                          <button
                            type="button"
                            onClick={() => handleWithdraw(chore.today_completion_id)}
                            aria-label="Withdraw this duty submission"
                            title="Withdraw — pulls it out of the queue so you can re-do it"
                            className="font-script text-tiny text-ink-whisper hover:text-ember-deep underline-offset-2 hover:underline transition-colors"
                          >
                            ↩ withdraw
                          </button>
                        )}
                      </div>
                    ) : isRejected ? (
                      <Button
                        size="sm"
                        onClick={() => handleComplete(chore.id)}
                        className="flex items-center gap-1 text-xs"
                      >
                        <RefreshCw size={12} /> Retry
                      </Button>
                    ) : isAvailable ? (
                      <Button
                        size="sm"
                        onClick={() => handleComplete(chore.id)}
                        className="flex items-center gap-1 text-xs"
                      >
                        <Check size={14} /> Done
                      </Button>
                    ) : null}
                  </div>
                </ParchmentCard>
              );
            })}
          </div>
        )}
      </section>

      {/* Child: recent history */}
      {!isParent && completions.length > 0 && (
        <section>
          <h2 className="font-display text-xl text-ink-primary leading-tight mb-3">
            Recent history
          </h2>
          <div className="space-y-2">
            {completions.slice(0, 10).map((c) => (
              <ParchmentCard key={c.id} className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-lg">{c.chore_icon || '📋'}</span>
                  <div className="min-w-0">
                    <div className="font-body text-sm font-medium text-ink-primary truncate">
                      {c.chore_title}
                    </div>
                    <div className="font-script text-xs text-ink-whisper">
                      {formatDate(c.completed_date)} · ${c.reward_amount_snapshot} + {c.coin_reward_snapshot} coins
                    </div>
                  </div>
                </div>
                <RuneBadge tone={STATUS_TONE[c.status] || 'ember'} size="sm">
                  {c.status}
                </RuneBadge>
              </ParchmentCard>
            ))}
          </div>
        </section>
      )}

      {showForm && (
        <ChoreFormModal
          chore={editingChore}
          children={children}
          skills={skills}
          isParent={isParent}
          mode={formMode}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); refresh(); }}
        />
      )}

      {deleteConfirm && (
        <ConfirmDialog
          title="Delete duty?"
          message="This will also remove all completion history for this duty."
          onConfirm={() => handleDelete(deleteConfirm)}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}
    </div>
  );
}
