import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ThumbsUp, ThumbsDown, Pencil, Trash2 } from 'lucide-react';
import {
  getHabits, createHabit, updateHabit, deleteHabit, logHabitTap, getChildren,
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

function HabitFormModal({ habit, children, onClose, onSaved }) {
  const isEdit = !!habit;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: habit?.name || '',
    icon: habit?.icon || '',
    habit_type: habit?.habit_type || 'positive',
    user: habit?.user ?? '',
    xp_reward: habit?.xp_reward ?? 5,
    max_taps_per_day: habit?.max_taps_per_day ?? 1,
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: form.name,
        icon: form.icon,
        habit_type: form.habit_type,
        user: form.user ? parseInt(form.user) : null,
        xp_reward: parseInt(form.xp_reward) || 0,
        max_taps_per_day: Math.max(1, parseInt(form.max_taps_per_day) || 1),
      };
      if (isEdit) {
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

  return (
    <BottomSheet title={isEdit ? 'Edit Ritual' : 'New Ritual'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Icon" value={form.icon} onChange={onField('icon')} placeholder="⚡" />
          <SelectField label="Type" value={form.habit_type} onChange={onField('habit_type')}>
            <option value="positive">Virtue (+)</option>
            <option value="negative">Vice (−)</option>
            <option value="both">Both</option>
          </SelectField>
        </div>
        {children?.length > 0 && (
          <SelectField label="Child" value={form.user} onChange={onField('user')}>
            <option value="">-- Select child --</option>
            {children.map((c) => (
              <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
            ))}
          </SelectField>
        )}
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Max taps / day" type="number" min="1" max="50" value={form.max_taps_per_day} onChange={onField('max_taps_per_day')} />
          <TextField label="XP reward" type="number" min="0" value={form.xp_reward} onChange={onField('xp_reward')} />
        </div>
        <Button type="submit" disabled={saving} className="w-full">
          {saving ? 'Saving…' : isEdit ? 'Update ritual' : 'Create ritual'}
        </Button>
      </form>
    </BottomSheet>
  );
}

export default function Habits() {
  const { isParent } = useRole();
  const { data: rawHabits, loading, reload } = useApi(getHabits);
  const { data: rawChildren } = useApi(isParent ? getChildren : null);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingHabit, setEditingHabit] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [tapping, setTapping] = useState(null);

  const habits = normalizeList(rawHabits);
  const children = normalizeList(rawChildren);

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
      reload();
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
        </div>
        {isParent && (
          <Button
            size="sm"
            onClick={() => { setEditingHabit(null); setShowForm(true); }}
            className="flex items-center gap-1.5"
          >
            <Plus size={16} /> New ritual
          </Button>
        )}
      </header>

      <ErrorAlert message={error} />

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
                          onClick={() => { setEditingHabit(habit); setShowForm(true); }}
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
          onClose={() => { setShowForm(false); setEditingHabit(null); }}
          onSaved={() => { setShowForm(false); setEditingHabit(null); reload(); }}
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
