import { useState } from 'react';
import { Target, Plus, Trash2 } from 'lucide-react';
import {
  getSavingsGoals, createSavingsGoal, deleteSavingsGoal,
} from '../../api';
import { useApi } from '../../hooks/useApi';
import { normalizeList } from '../../utils/api';
import { formatCurrency } from '../../utils/format';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import ConfirmDialog from '../../components/ConfirmDialog';
import ParchmentCard from '../../components/journal/ParchmentCard';
import QuillProgress from '../../components/QuillProgress';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { TextField } from '../../components/form';

// Coin-per-dollar multiplier for the completion bonus. Mirrored from
// ``settings.COINS_PER_SAVINGS_GOAL_DOLLAR`` — when/if this tunable moves,
// surface it via the /api/dashboard/ or /api/settings/ payload instead of
// hardcoding it in two places.
const COINS_PER_DOLLAR = 2;

function coinBonusFor(target) {
  const n = Number(target || 0);
  return Number.isFinite(n) ? Math.round(n * COINS_PER_DOLLAR) : 0;
}

function GoalCard({ goal, onDelete }) {
  const current = Number(goal.current_amount ?? 0);
  const target = Number(goal.target_amount);
  return (
    <ParchmentCard seal className="relative">
      <div className="flex items-start gap-2 mb-2">
        {goal.icon && <span className="text-2xl shrink-0">{goal.icon}</span>}
        <Target size={18} className="text-moss shrink-0 mt-1" />
        <span className="font-display text-base leading-tight flex-1 min-w-0">
          {goal.title}
        </span>
        <IconButton
          variant="ghost"
          size="sm"
          aria-label={`Remove ${goal.title}`}
          onClick={() => onDelete(goal)}
        >
          <Trash2 size={14} />
        </IconButton>
      </div>
      <div className="flex justify-between font-rune text-tiny text-ink-whisper mb-1">
        <span>{formatCurrency(current)}</span>
        <span>{formatCurrency(target)}</span>
      </div>
      <QuillProgress
        value={current}
        max={target}
        color="bg-gradient-to-r from-moss to-gold-leaf"
        aria-label={`${goal.title} progress`}
      />
      <p className="mt-2 font-script text-caption text-ink-whisper">
        Hit the target to earn <span className="text-gold-leaf font-semibold">+{coinBonusFor(target)} coins</span>.
      </p>
    </ParchmentCard>
  );
}

function CompletedGoal({ goal }) {
  const completed = goal.completed_at
    ? new Date(goal.completed_at).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
      })
    : '—';
  return (
    <li className="flex items-center gap-3 py-2 border-b border-ink-page-shadow/40 last:border-b-0">
      {goal.icon && <span className="text-xl shrink-0">{goal.icon}</span>}
      <div className="flex-1 min-w-0">
        <div className="font-display text-body truncate">{goal.title}</div>
        <div className="font-script text-caption text-ink-whisper">
          {formatCurrency(goal.target_amount)} · completed {completed}
        </div>
      </div>
      <div className="font-rune text-tiny text-gold-leaf shrink-0">
        +{coinBonusFor(goal.target_amount)}c
      </div>
    </li>
  );
}

function CreateGoalSheet({ onClose, onCreated }) {
  const [title, setTitle] = useState('');
  const [target, setTarget] = useState('');
  const [icon, setIcon] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const numericTarget = Number(target);
    if (!title.trim()) {
      setError('Give your hoard a name.');
      return;
    }
    if (!Number.isFinite(numericTarget) || numericTarget <= 0) {
      setError('Target must be a positive number.');
      return;
    }
    setBusy(true);
    try {
      await createSavingsGoal({
        title: title.trim(),
        target_amount: numericTarget,
        icon: icon.trim(),
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err?.message || 'Could not create hoard.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <BottomSheet title="Start a new hoard" onClose={onClose} disabled={busy}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField
          label="What are you saving for?"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Lego set, bike, headphones…"
          autoFocus
        />
        <TextField
          label="Target amount"
          type="number"
          step="0.01"
          min="0"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="25.00"
        />
        <TextField
          label="Icon (optional emoji)"
          value={icon}
          onChange={(e) => setIcon(e.target.value)}
          placeholder="🧱"
          maxLength={4}
        />
        {error && <ErrorAlert>{error}</ErrorAlert>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" type="button" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? 'Creating…' : 'Start saving'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

/**
 * HoardsTab — child's savings goals, rendered as the 4th tab of Treasury.
 *
 * Design model: aspirational balance tracker. Money stays fully liquid;
 * ``current_amount`` is computed server-side from the live payment
 * balance. Crossing a goal's target auto-fires the completion pipeline
 * (coin bonus + badge evaluation + notification) from
 * ``SavingsGoalService.check_and_complete``.
 */
export default function HoardsTab() {
  const { data, loading, error, reload } = useApi(getSavingsGoals);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  if (loading) return <Loader />;
  if (error) return <ErrorAlert>{error}</ErrorAlert>;

  const goals = normalizeList(data);
  const active = goals.filter((g) => !g.is_completed);
  const completed = goals.filter((g) => g.is_completed)
    .sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at));

  const handleDeleteConfirm = async () => {
    const goal = pendingDelete;
    setPendingDelete(null);
    if (!goal) return;
    try {
      await deleteSavingsGoal(goal.id);
      reload();
    } catch (err) {
      // Swallow — reload will re-fetch truth from the server.
      reload();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-lede text-ink-primary">
            Your hoards
          </h2>
          <p className="font-script text-caption text-ink-whisper">
            Goals grow as your balance grows — hit the target and you'll
            earn a coin bonus.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setSheetOpen(true)}
          aria-label="Start a new hoard"
        >
          <Plus size={16} /> New hoard
        </Button>
      </div>

      {active.length === 0 ? (
        <ParchmentCard className="text-center py-8">
          <Target size={28} className="mx-auto mb-2 text-moss" />
          <p className="font-display text-body text-ink-primary">
            No active hoards yet.
          </p>
          <p className="font-script text-caption text-ink-whisper mt-1">
            Set one up and your balance will fill it in automatically.
          </p>
        </ParchmentCard>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          {active.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              onDelete={setPendingDelete}
            />
          ))}
        </div>
      )}

      {completed.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer font-display text-body text-ink-primary mb-2">
            Completed hoards
            <span className="ml-2 font-rune text-caption text-ink-whisper">
              ({completed.length})
            </span>
          </summary>
          <ParchmentCard>
            <ul className="divide-y divide-ink-page-shadow/40">
              {completed.map((goal) => (
                <CompletedGoal key={goal.id} goal={goal} />
              ))}
            </ul>
          </ParchmentCard>
        </details>
      )}

      {sheetOpen && (
        <CreateGoalSheet
          onClose={() => setSheetOpen(false)}
          onCreated={reload}
        />
      )}
      {pendingDelete && (
        <ConfirmDialog
          title={`Remove "${pendingDelete.title}"?`}
          message="This removes the goal from your hoard list. Your balance stays put."
          confirmLabel="Remove"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
