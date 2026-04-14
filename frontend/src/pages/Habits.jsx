import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ThumbsUp, ThumbsDown, Pencil, Trash2, Zap } from 'lucide-react';
import {
  getHabits, createHabit, updateHabit, deleteHabit, logHabitTap, getChildren,
} from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import ConfirmDialog from '../components/ConfirmDialog';
import FormModal from '../components/FormModal';
import { inputClass } from '../constants/styles';
import { normalizeList } from '../utils/api';

function getStrengthColor(strength) {
  if (strength < -5) return 'bg-red-700 text-white';
  if (strength < 0) return 'bg-red-400 text-white';
  if (strength === 0) return 'bg-yellow-400 text-gray-900';
  if (strength <= 5) return 'bg-green-400 text-white';
  if (strength <= 10) return 'bg-green-600 text-white';
  return 'bg-blue-600 text-white';
}

function HabitFormModal({ habit, children, onClose, onSaved }) {
  const isEdit = !!habit;
  const [form, setForm] = useState({
    name: habit?.name || '',
    icon: habit?.icon || '',
    habit_type: habit?.habit_type || 'positive',
    user: habit?.user ?? '',
    coin_reward: habit?.coin_reward ?? 2,
    xp_reward: habit?.xp_reward ?? 5,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = {
        name: form.name,
        icon: form.icon,
        habit_type: form.habit_type,
        user: form.user ? parseInt(form.user) : null,
        coin_reward: parseInt(form.coin_reward) || 0,
        xp_reward: parseInt(form.xp_reward) || 0,
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
    <FormModal title={isEdit ? 'Edit Habit' : 'New Habit'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Name</label>
              <input className={inputClass} value={form.name} onChange={set('name')} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Icon</label>
                <input className={inputClass} value={form.icon} onChange={set('icon')} placeholder="⚡" />
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Type</label>
                <select className={inputClass} value={form.habit_type} onChange={set('habit_type')}>
                  <option value="positive">Positive</option>
                  <option value="negative">Negative</option>
                  <option value="both">Both</option>
                </select>
              </div>
            </div>
            {children?.length > 0 && (
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Child</label>
                <select className={inputClass} value={form.user} onChange={set('user')}>
                  <option value="">-- Select child --</option>
                  {children.map((c) => (
                    <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Coin Reward</label>
                <input className={inputClass} type="number" min="0" value={form.coin_reward} onChange={set('coin_reward')} />
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">XP Reward</label>
                <input className={inputClass} type="number" min="0" value={form.xp_reward} onChange={set('xp_reward')} />
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="w-full py-2 bg-amber-primary hover:bg-amber-primary/80 text-white font-semibold rounded-lg disabled:opacity-50"
            >
              {saving ? 'Saving...' : isEdit ? 'Update Habit' : 'Create Habit'}
            </button>
          </form>
    </FormModal>
  );
}

export default function Habits() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';
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
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold text-forge-text flex items-center gap-2">
          <Zap size={24} /> Habits
        </h1>
        {isParent && (
          <button
            onClick={() => { setEditingHabit(null); setShowForm(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-primary hover:bg-amber-primary/80 text-white text-sm font-semibold rounded-lg"
          >
            <Plus size={16} /> New Habit
          </button>
        )}
      </div>

      <ErrorAlert message={error} />

      {habits.length === 0 ? (
        <EmptyState icon={Zap} message="No habits yet" />
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
                <Card>
                  <div className="flex items-start gap-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${getStrengthColor(habit.strength ?? 0)}`}>
                      {habit.strength ?? 0}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {habit.icon && <span className="text-lg">{habit.icon}</span>}
                        <span className="font-semibold truncate">{habit.name}</span>
                      </div>
                      <div className="text-xs text-forge-text-dim mt-0.5">
                        {habit.coin_reward > 0 && <span>{habit.coin_reward} coins</span>}
                        {habit.coin_reward > 0 && habit.xp_reward > 0 && <span> / </span>}
                        {habit.xp_reward > 0 && <span>{habit.xp_reward} XP</span>}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-forge-border">
                    <div className="flex gap-2">
                      {(habit.habit_type === 'positive' || habit.habit_type === 'both') && (
                        <button
                          onClick={() => handleTap(habit, 'up')}
                          disabled={tapping === `${habit.id}-up`}
                          className="flex items-center gap-1 px-3 py-1.5 bg-green-500/20 hover:bg-green-500/30 text-green-400 text-sm font-medium rounded-lg disabled:opacity-50"
                        >
                          <ThumbsUp size={14} /> +
                        </button>
                      )}
                      {(habit.habit_type === 'negative' || habit.habit_type === 'both') && (
                        <button
                          onClick={() => handleTap(habit, 'down')}
                          disabled={tapping === `${habit.id}-down`}
                          className="flex items-center gap-1 px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 text-sm font-medium rounded-lg disabled:opacity-50"
                        >
                          <ThumbsDown size={14} /> -
                        </button>
                      )}
                    </div>
                    {isParent && (
                      <div className="flex gap-1">
                        <button
                          onClick={() => { setEditingHabit(habit); setShowForm(true); }}
                          className="p-1.5 text-forge-text-dim hover:text-forge-text rounded"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(habit)}
                          className="p-1.5 text-forge-text-dim hover:text-red-400 rounded"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </Card>
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
          title="Delete Habit"
          message={`Are you sure you want to delete "${confirmDelete.name}"?`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
