import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  ClipboardCheck, Check, Plus, Pencil, Trash2,
  DollarSign, Coins, CalendarDays, RefreshCw,
} from 'lucide-react';
import {
  getChores, createChore, updateChore, deleteChore, completeChore,
  getChoreCompletions, approveChoreCompletion, rejectChoreCompletion,
  getChildren,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useFormState } from '../hooks/useFormState';
import { useRole } from '../hooks/useRole';
import ApprovalButtons from '../components/ApprovalButtons';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import FormModal from '../components/FormModal';
import { STATUS_COLORS } from '../constants/colors';
import { formatDate } from '../utils/format';
import { normalizeList } from '../utils/api';
import { buttonPrimary, inputClass } from '../constants/styles';

const RECURRENCE_LABELS = { daily: 'Daily', weekly: 'Weekly', one_time: 'One-Time' };
const WEEK_SCHEDULE_LABELS = { every_week: 'Every Week', alternating: 'Alternating Weeks' };

function ChoreFormModal({ chore, children, onClose, onSaved }) {
  const isEdit = !!chore;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: chore?.title || '',
    description: chore?.description || '',
    icon: chore?.icon || '',
    reward_amount: chore?.reward_amount ?? '1.00',
    coin_reward: chore?.coin_reward ?? 2,
    recurrence: chore?.recurrence || 'daily',
    week_schedule: chore?.week_schedule || 'every_week',
    schedule_start_date: chore?.schedule_start_date || '',
    assigned_to: chore?.assigned_to ?? '',
    is_active: chore?.is_active ?? true,
    order: chore?.order ?? 0,
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
      const payload = {
        title: form.title,
        description: form.description,
        icon: form.icon,
        reward_amount: form.reward_amount,
        coin_reward: parseInt(form.coin_reward) || 0,
        recurrence: form.recurrence,
        week_schedule: form.recurrence === 'one_time' ? 'every_week' : form.week_schedule,
        schedule_start_date: form.week_schedule === 'alternating' && form.recurrence !== 'one_time'
          ? form.schedule_start_date || null : null,
        assigned_to: form.assigned_to ? parseInt(form.assigned_to) : null,
        is_active: form.is_active,
        order: parseInt(form.order) || 0,
      };
      if (isEdit) {
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

  return (
    <FormModal title={isEdit ? 'Edit Chore' : 'New Chore'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Title</label>
              <input className={inputClass} value={form.title} onChange={onField('title')} required />
            </div>
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Description</label>
              <textarea className={inputClass} value={form.description} onChange={onField('description')} rows={2} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Icon</label>
                <input className={inputClass} value={form.icon} onChange={onField('icon')} placeholder="🧹" />
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Reward ($)</label>
                <input className={inputClass} type="number" min="0" step="0.25" value={form.reward_amount} onChange={onField('reward_amount')} />
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Coins</label>
                <input className={inputClass} type="number" min="0" value={form.coin_reward} onChange={onField('coin_reward')} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Recurrence</label>
                <select className={inputClass} value={form.recurrence} onChange={onField('recurrence')}>
                  {Object.entries(RECURRENCE_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Assign To</label>
                <select className={inputClass} value={form.assigned_to} onChange={onField('assigned_to')}>
                  <option value="">All Children</option>
                  {children.map((c) => (
                    <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
                  ))}
                </select>
              </div>
            </div>
            {showSchedule && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-forge-text-dim mb-1 block">Custody Schedule</label>
                  <select className={inputClass} value={form.week_schedule} onChange={onField('week_schedule')}>
                    {Object.entries(WEEK_SCHEDULE_LABELS).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </div>
                {form.week_schedule === 'alternating' && (
                  <div>
                    <label className="text-xs text-forge-text-dim mb-1 block">Start Date (on-week)</label>
                    <input className={inputClass} type="date" value={form.schedule_start_date} onChange={onField('schedule_start_date')} />
                  </div>
                )}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Order</label>
                <input className={inputClass} type="number" value={form.order} onChange={onField('order')} />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.is_active} onChange={onField('is_active')} className="accent-amber-primary" />
                  Active
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">Cancel</button>
              <button type="submit" disabled={saving} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
                {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
    </FormModal>
  );
}

export default function Chores() {
  const { isParent } = useRole();

  const { data: choresData, loading: loadingChores, reload: reloadChores } = useApi(getChores);
  const { data: completionsData, loading: loadingCompletions, reload: reloadCompletions } = useApi(
    isParent ? () => getChoreCompletions('pending') : () => getChoreCompletions(),
    [isParent],
  );
  const { data: childrenData } = useApi(isParent ? getChildren : () => Promise.resolve([]), [isParent]);

  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingChore, setEditingChore] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const loading = loadingChores || loadingCompletions;

  const refresh = () => {
    reloadChores();
    reloadCompletions();
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
  const children = normalizeList(childrenData);
  const pendingCompletions = completions.filter((c) => c.status === 'pending');

  // Child view: count done vs total
  const doneCount = chores.filter((c) => c.is_done || c.today_status === 'approved' || c.today_status === 'pending').length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Chores</h1>
        {isParent && (
          <button
            onClick={() => { setEditingChore(null); setShowForm(true); }}
            className={`flex items-center gap-1 px-3 py-1.5 text-xs ${buttonPrimary}`}
          >
            <Plus size={14} /> New Chore
          </button>
        )}
      </div>

      <ErrorAlert message={error} />

      {/* Child summary card */}
      {!isParent && chores.length > 0 && (
        <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
          <Card className="text-center py-5">
            <div className="text-xs text-forge-text-dim mb-1 flex items-center justify-center gap-1">
              <ClipboardCheck size={14} /> Today&apos;s Progress
            </div>
            <div className="font-heading text-4xl font-bold text-amber-highlight">
              {doneCount} <span className="text-lg text-forge-text-dim">/ {chores.length}</span>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Parent: pending approvals */}
      {isParent && pendingCompletions.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Pending Approvals</h2>
          <div className="space-y-2">
            {pendingCompletions.map((c) => (
              <Card key={c.id} className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">
                    {c.user_name} — {c.chore_icon} {c.chore_title}
                  </div>
                  <div className="text-xs text-forge-text-dim">
                    {formatDate(c.completed_date)} — ${c.reward_amount_snapshot} + {c.coin_reward_snapshot} coins
                  </div>
                  {c.notes && (
                    <div className="text-xs text-forge-text-dim italic mt-0.5">&ldquo;{c.notes}&rdquo;</div>
                  )}
                </div>
                <div className="shrink-0">
                  <ApprovalButtons onApprove={() => handleApprove(c.id)} onReject={() => handleReject(c.id)} />
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Chore list */}
      <div>
        <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
          <ClipboardCheck size={18} /> {isParent ? 'All Chores' : 'Today\u2019s Chores'}
        </h2>
        {chores.length === 0 ? (
          <EmptyState>
            {isParent ? 'No chores created yet. Add one to get started!' : 'No chores available today.'}
          </EmptyState>
        ) : (
          <div className="space-y-2">
            {chores.map((chore) => {
              const isDone = !isParent && (chore.today_status === 'approved' || chore.today_status === 'pending');
              const isAvailable = !isParent && chore.is_available;
              const isRejected = !isParent && chore.today_status === 'rejected';
              return (
                <Card key={chore.id} className={`flex items-center gap-3 ${isDone ? 'opacity-60' : ''}`}>
                  <div className="text-2xl shrink-0 w-10 text-center">{chore.icon || '📋'}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium flex items-center gap-2">
                      {chore.title}
                      {isParent && !chore.is_active && (
                        <span className="text-[10px] text-red-400">Inactive</span>
                      )}
                    </div>
                    {chore.description && (
                      <div className="text-xs text-forge-text-dim line-clamp-1">{chore.description}</div>
                    )}
                    <div className="flex items-center gap-3 mt-1 text-xs text-forge-text-dim">
                      <span className="flex items-center gap-0.5">
                        <DollarSign size={10} />{chore.reward_amount}
                      </span>
                      <span className="flex items-center gap-0.5">
                        <Coins size={10} />{chore.coin_reward}
                      </span>
                      <span className="flex items-center gap-0.5">
                        <RefreshCw size={10} />{RECURRENCE_LABELS[chore.recurrence]}
                      </span>
                      {chore.week_schedule === 'alternating' && (
                        <span className="flex items-center gap-0.5">
                          <CalendarDays size={10} />Alt. weeks
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
                          onClick={() => { setEditingChore(chore); setShowForm(true); }}
                          className="p-1.5 bg-forge-bg hover:bg-forge-muted rounded text-forge-text-dim hover:text-forge-text"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(chore.id)}
                          className="p-1.5 bg-forge-bg hover:bg-red-500/30 rounded text-forge-text-dim hover:text-red-300"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ) : isDone ? (
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[chore.today_status] || STATUS_COLORS.pending}`}>
                        {chore.today_status}
                      </span>
                    ) : isRejected ? (
                      <button
                        onClick={() => handleComplete(chore.id)}
                        className={`flex items-center gap-1 px-3 py-1.5 text-xs ${buttonPrimary}`}
                      >
                        <RefreshCw size={12} /> Retry
                      </button>
                    ) : isAvailable ? (
                      <button
                        onClick={() => handleComplete(chore.id)}
                        className={`flex items-center gap-1 px-3 py-1.5 text-xs ${buttonPrimary}`}
                      >
                        <Check size={14} /> Done
                      </button>
                    ) : null}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Child: recent history */}
      {!isParent && completions.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Recent History</h2>
          <div className="space-y-2">
            {completions.slice(0, 10).map((c) => (
              <Card key={c.id} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{c.chore_icon || '📋'}</span>
                  <div>
                    <div className="text-sm font-medium">{c.chore_title}</div>
                    <div className="text-xs text-forge-text-dim">
                      {formatDate(c.completed_date)} — ${c.reward_amount_snapshot} + {c.coin_reward_snapshot} coins
                    </div>
                  </div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[c.status] || STATUS_COLORS.pending}`}>
                  {c.status}
                </span>
              </Card>
            ))}
          </div>
        </div>
      )}

      {showForm && (
        <ChoreFormModal
          chore={editingChore}
          children={children}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); refresh(); }}
        />
      )}

      {deleteConfirm && (
        <ConfirmDialog
          title="Delete Chore?"
          message="This will also remove all completion history for this chore."
          onConfirm={() => handleDelete(deleteConfirm)}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}
    </div>
  );
}
