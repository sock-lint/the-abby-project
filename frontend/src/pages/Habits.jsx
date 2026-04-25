import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ThumbsUp, ThumbsDown, Pencil, Trash2 } from 'lucide-react';
import {
  getHabits, createHabit, updateHabit, deleteHabit, logHabitTap,
  listMyHabitProposals, listPendingHabitProposals, approveHabitProposal,
  getChildren, getSkills,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useFormState } from '../hooks/useFormState';
import { useRole } from '../hooks/useRole';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import ConfirmDialog from '../components/ConfirmDialog';
import BottomSheet from '../components/BottomSheet';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import SkillTagEditor from '../components/SkillTagEditor';
import { ScrollIcon } from '../components/icons/JournalIcons';
import Button from '../components/Button';
import { TextField, SelectField } from '../components/form';
import { normalizeList } from '../utils/api';

// Strength color — journal-safe sepia gradient from ember (low) through
// moss (positive) to royal (mastered).
function getStrengthColor(strength) {
  if (strength < -5) return 'bg-ember-deep text-ink-page-rune-glow';
  if (strength < 0)  return 'bg-ember text-ink-page-rune-glow';
  if (strength === 0) return 'bg-gold-leaf text-ink-primary';
  if (strength <= 5) return 'bg-moss/80 text-ink-page-rune-glow';
  if (strength <= 10) return 'bg-moss text-ink-page-rune-glow';
  return 'bg-royal text-ink-page-rune-glow';
}

function HabitFormModal({ habit, children, skills, isParent, mode, onClose, onSaved }) {
  const resolvedMode = mode || (habit ? 'edit' : 'create');
  const isApprove = resolvedMode === 'approve';
  const isEdit = resolvedMode === 'edit';
  const canSetRewards = isParent;

  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: habit?.name || '',
    icon: habit?.icon || '',
    habit_type: habit?.habit_type || 'positive',
    user: habit?.user ?? '',
    xp_reward: habit?.xp_reward ?? 5,
    max_taps_per_day: habit?.max_taps_per_day ?? 1,
    skill_tags: (habit?.skill_tags || []).map((t) => ({
      skill_id: t.skill,
      xp_weight: t.xp_weight,
    })),
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const base = {
        name: form.name,
        icon: form.icon,
        habit_type: form.habit_type,
        max_taps_per_day: Math.max(1, parseInt(form.max_taps_per_day) || 1),
      };
      const parentExtras = canSetRewards ? {
        user: form.user ? parseInt(form.user) : null,
        xp_reward: parseInt(form.xp_reward) || 0,
        skill_tags: form.skill_tags,
      } : {};
      const payload = { ...base, ...parentExtras };

      if (isApprove) {
        await approveHabitProposal(habit.id, payload);
      } else if (isEdit) {
        await updateHabit(habit.id, payload);
      } else {
        await createHabit(payload);
      }
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const title = isApprove
    ? 'Approve ritual proposal'
    : isEdit
      ? 'Edit Ritual'
      : isParent ? 'New Ritual' : 'Propose a Ritual';
  const submitLabel = isApprove
    ? 'Approve & publish'
    : isEdit ? 'Update ritual'
    : isParent ? 'Create ritual' : 'Send to parent';

  return (
    <BottomSheet title={title} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        {isApprove && habit?.created_by_name && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-sm text-ink-primary">
            Proposed by <span className="font-body font-medium">{habit.created_by_name}</span>
            {' — set XP + skill tags below and publish to their ritual list.'}
          </div>
        )}
        {!canSetRewards && !isApprove && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-sm text-ink-primary">
            Your parent will set the rewards when they approve this.
          </div>
        )}
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Icon" value={form.icon} onChange={onField('icon')} placeholder="⚡" />
          <SelectField label="Type" value={form.habit_type} onChange={onField('habit_type')}>
            <option value="positive">Virtue (+)</option>
            <option value="negative">Vice (−)</option>
            <option value="both">Both</option>
          </SelectField>
        </div>
        <TextField
          label="Max taps / day"
          type="number"
          min="1"
          max="50"
          value={form.max_taps_per_day}
          onChange={onField('max_taps_per_day')}
        />
        {canSetRewards && children?.length > 0 && (
          <SelectField label="Child" value={form.user} onChange={onField('user')}>
            <option value="">-- Select child --</option>
            {children.map((c) => (
              <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
            ))}
          </SelectField>
        )}
        {canSetRewards && (
          <>
            <TextField label="XP pool" type="number" min="0" value={form.xp_reward} onChange={onField('xp_reward')} />
            <SkillTagEditor
              skills={skills}
              value={form.skill_tags}
              onChange={(tags) => set({ skill_tags: tags })}
            />
          </>
        )}
        <Button type="submit" disabled={saving} className="w-full">
          {saving ? 'Saving…' : submitLabel}
        </Button>
      </form>
    </BottomSheet>
  );
}

export default function Habits() {
  const { isParent } = useRole();
  const { data: rawHabits, loading, reload } = useApi(getHabits);
  const { data: rawProposals, reload: reloadProposals } = useApi(
    isParent ? listPendingHabitProposals : listMyHabitProposals,
    [isParent],
  );
  const { data: rawChildren } = useApi(isParent ? getChildren : null);
  const { data: rawSkills } = useApi(isParent ? getSkills : null);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingHabit, setEditingHabit] = useState(null);
  const [formMode, setFormMode] = useState('create');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [tapping, setTapping] = useState(null);

  const habits = normalizeList(rawHabits);
  const proposals = normalizeList(rawProposals);
  const children = normalizeList(rawChildren);
  const skills = normalizeList(rawSkills);

  const refreshAll = () => {
    reload();
    reloadProposals();
  };

  const openCreate = () => {
    setEditingHabit(null);
    setFormMode('create');
    setShowForm(true);
  };
  const openEdit = (habit) => {
    setEditingHabit(habit);
    setFormMode('edit');
    setShowForm(true);
  };
  const openApprove = (habit) => {
    setEditingHabit(habit);
    setFormMode('approve');
    setShowForm(true);
  };

  const handleTap = async (habit, direction) => {
    setTapping(`${habit.id}-${direction}`);
    setError('');
    try {
      await logHabitTap(habit.id, direction);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setTapping(null);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setError('');
    try {
      await deleteHabit(confirmDelete.id);
      setConfirmDelete(null);
      refreshAll();
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) return <Loader />;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            rituals · virtues & vices
          </div>
          <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
            Rituals
          </h2>
          <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
            tap a virtue to strengthen it; missed days drift it back · colour shows the current pull
          </div>
        </div>
        <Button
          size="sm"
          onClick={openCreate}
          className="flex items-center gap-1.5"
        >
          <Plus size={16} /> {isParent ? 'New ritual' : 'Propose a ritual'}
        </Button>
      </header>

      <ErrorAlert message={error} />

      {proposals.length > 0 && (
        <section aria-labelledby="habit-proposals-heading">
          <h3
            id="habit-proposals-heading"
            className="font-display text-lg text-ink-primary mb-3"
          >
            {isParent ? 'Ritual proposals awaiting review' : 'Your proposals'}
          </h3>
          <div className="space-y-2">
            {proposals.map((p) => (
              <ParchmentCard key={p.id} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-body text-sm font-medium text-ink-primary flex items-center gap-2">
                    <span className="text-lg">{p.icon || '⚡'}</span>
                    {p.name}
                    <RuneBadge tone="ember" size="sm">pending</RuneBadge>
                  </div>
                  <div className="font-script text-xs text-ink-whisper">
                    {isParent
                      ? `proposed by ${p.created_by_name || 'child'}`
                      : 'waiting for parent to set XP'}
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
                        onClick={() => setConfirmDelete(p)}
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

      {habits.length === 0 ? (
        <EmptyState icon={<ScrollIcon size={32} />}>
          No rituals recorded yet. Inscribe a virtue to begin practicing.
        </EmptyState>
      ) : (
        <motion.div layout className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          <AnimatePresence>
            {habits.map((habit) => (
              <motion.div
                key={habit.id}
                layout
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
              >
                <ParchmentCard>
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-11 h-11 rounded-full flex items-center justify-center font-rune text-sm font-bold shrink-0 shadow-sm ${getStrengthColor(habit.strength ?? 0)}`}
                    >
                      {habit.strength ?? 0}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {habit.icon && <span className="text-lg">{habit.icon}</span>}
                        <span className="font-display text-base text-ink-primary truncate">
                          {habit.name}
                        </span>
                      </div>
                      <div className="font-script text-xs text-ink-whisper mt-0.5">
                        {habit.xp_reward > 0 && <span>{habit.xp_reward} XP</span>}
                        {habit.xp_reward > 0 && habit.max_taps_per_day > 0 && <span> · </span>}
                        {habit.max_taps_per_day > 0 && (
                          <span>
                            {habit.taps_today ?? 0}/{habit.max_taps_per_day} today
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-ink-page-shadow/70">
                    <div className="flex gap-2">
                      {(habit.habit_type === 'positive' || habit.habit_type === 'both') && (() => {
                        const atCap = (habit.taps_today ?? 0) >= (habit.max_taps_per_day ?? 1);
                        return (
                          <button
                            type="button"
                            onClick={() => handleTap(habit, 1)}
                            disabled={tapping === `${habit.id}-1` || atCap}
                            title={atCap ? `Daily limit reached (${habit.max_taps_per_day}/day)` : undefined}
                            className="flex items-center gap-1 px-3 py-1.5 bg-moss/20 hover:bg-moss/30 text-moss text-sm font-body font-medium rounded-lg border border-moss/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            <ThumbsUp size={14} /> {atCap ? 'done' : 'virtue'}
                          </button>
                        );
                      })()}
                      {(habit.habit_type === 'negative' || habit.habit_type === 'both') && (
                        <button
                          type="button"
                          onClick={() => handleTap(habit, -1)}
                          disabled={tapping === `${habit.id}--1`}
                          className="flex items-center gap-1 px-3 py-1.5 bg-ember/20 hover:bg-ember/30 text-ember-deep text-sm font-body font-medium rounded-lg border border-ember/40 disabled:opacity-50 transition-colors"
                        >
                          <ThumbsDown size={14} /> vice
                        </button>
                      )}
                    </div>
                    {isParent && (
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(habit)}
                          aria-label="Edit ritual"
                          className="p-1.5 text-ink-secondary hover:text-ink-primary transition-colors"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDelete(habit)}
                          aria-label="Delete ritual"
                          className="p-1.5 text-ink-secondary hover:text-ember-deep transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </ParchmentCard>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {showForm && (
        <HabitFormModal
          habit={editingHabit}
          children={isParent ? children : null}
          skills={skills}
          isParent={isParent}
          mode={formMode}
          onClose={() => { setShowForm(false); setEditingHabit(null); }}
          onSaved={() => { setShowForm(false); setEditingHabit(null); refreshAll(); }}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete ritual"
          message={`Are you sure you want to delete "${confirmDelete.name}"?`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
