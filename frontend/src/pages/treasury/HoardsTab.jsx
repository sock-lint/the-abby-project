import { useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
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
import { TextField, IconPicker } from '../../components/form';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';
import IncipitBand from '../../components/atlas/IncipitBand';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import {
  tierForProgress,
  RARITY_HALO,
  isRecentlyEarned,
} from '../../components/atlas/mastery.constants';

function clampPct(pct) {
  if (!Number.isFinite(pct)) return 0;
  return Math.max(0, Math.min(100, pct));
}

function GoalCard({ goal, onDelete }) {
  const current = Number(goal.current_amount ?? 0);
  const target = Number(goal.target_amount);
  const pct = clampPct(target > 0 ? (current / target) * 100 : 0);
  const tier = tierForProgress({ unlocked: true, progressPct: pct });
  // First letter of the title drives the versal glyph; the emoji icon stays
  // inline with the title rather than competing with the gilt drop-cap.
  const versalLetter = (goal.title || '✦').trim().slice(0, 1) || '✦';
  return (
    <ParchmentCard variant="sealed" tone="default" className="relative">
      <div className="flex items-start gap-4">
        <IlluminatedVersal
          letter={versalLetter}
          progressPct={pct}
          tier={tier}
          size="lg"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-display italic text-lede text-ink-primary leading-tight flex items-center gap-2 min-w-0">
              {goal.icon && (
                <span aria-hidden="true" className="text-xl leading-none shrink-0">
                  {goal.icon}
                </span>
              )}
              <span className="truncate">{goal.title}</span>
            </h3>
            <IconButton
              variant="ghost"
              size="sm"
              aria-label={`Remove ${goal.title}`}
              onClick={() => onDelete(goal)}
            >
              <Trash2 size={14} />
            </IconButton>
          </div>
          <div className="mt-1 flex justify-between font-rune text-tiny text-ink-whisper">
            <span>{formatCurrency(current)}</span>
            <span>of {formatCurrency(target)}</span>
          </div>
          <QuillProgress
            value={current}
            max={target}
            aria-label={`${goal.title} progress`}
          />
          <p className="mt-2 font-script text-caption text-ink-whisper">
            Coin bonuses celebrate new savings milestones.
          </p>
        </div>
      </div>
    </ParchmentCard>
  );
}

/**
 * CompletedHoardSeal — local riff on BadgeSigil's earned-state shell. A
 * savings goal that crossed the line is rare by definition, so every seal
 * wears the legendary halo. Seals completed in the last 7 days play the
 * gilded-glint one-shot, just like a freshly-earned badge.
 *
 * Lives here rather than being a refactor of BadgeSigil because the API
 * shape (goal vs badge) and the static "legendary always" treatment make
 * a shared abstraction premature — promote on the third consumer.
 */
function CompletedHoardSeal({ goal }) {
  const recent = isRecentlyEarned(goal.completed_at);
  const completed = goal.completed_at
    ? new Date(goal.completed_at).toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
      })
    : '—';
  return (
    <div
      data-hoard-seal="true"
      data-recent={recent ? 'true' : 'false'}
      className={`relative rounded-2xl p-3 flex flex-col items-center gap-1.5 min-h-[148px] bg-ink-page-rune-glow/95 border border-ink-page-shadow ${RARITY_HALO.legendary} ${recent ? 'animate-gilded-glint' : ''}`}
    >
      <div className="relative w-14 h-14 rounded-full flex items-center justify-center bg-ink-page-aged shadow-[inset_0_1px_0_rgba(255,248,224,0.6),inset_0_-2px_4px_rgba(45,31,21,0.15)]">
        <span aria-hidden="true" className="text-3xl leading-none">
          {goal.icon || '🏆'}
        </span>
      </div>
      <div className="text-caption text-center font-medium leading-tight line-clamp-2 text-ink-primary">
        {goal.title}
      </div>
      <div className="text-micro font-script italic text-center text-ink-whisper/80 leading-snug">
        Completed {completed}
      </div>
      <div className="mt-auto pt-1 text-micro font-rune uppercase tracking-wider text-gold-leaf">
        Goal reached · {formatCurrency(goal.target_amount)}
      </div>
    </div>
  );
}

function CreateGoalSheet({ onClose, onCreated }) {
  const [title, setTitle] = useState('');
  const [target, setTarget] = useState('');
  const [icon, setIcon] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dirty = Boolean(title || target || icon);
  usePwaUpdateGuard(dirty || busy);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const numericTarget = Number(target);
    if (!title.trim()) {
      setError('Give your savings goal a name.');
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
      setError(err?.message || 'Could not create savings goal.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <BottomSheet title="New savings goal" onClose={onClose} disabled={busy} dirty={dirty}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className="text-caption text-ink-secondary">
          Coin bonuses reward new savings. Goals already covered by your balance do not earn another bonus.
        </p>
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
        <IconPicker
          label="Icon (optional emoji)"
          value={icon}
          onChange={setIcon}
          placeholder="🧱"
          maxLength={4}
          disabled={busy}
        />
        {/* ErrorAlert renders its `message` prop and nothing else — passing
            the text as children made submit failures render as literally
            nothing and the sheet just sat there. */}
        <ErrorAlert message={error} />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" type="button" onClick={onClose} disabled={busy}>
            {dirty ? 'Discard draft' : 'Cancel'}
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
 * HoardsTab — child's savings goals, rendered as the 5th tab of Treasury.
 *
 * Design model: aspirational balance tracker. Money stays fully liquid;
 * ``current_amount`` is computed server-side from the live payment
 * balance. Explicit goal and balance writes settle server-owned milestone
 * rewards. Displaying a completed goal does not imply a Coin payout.
 *
 * Visual model: illuminated-manuscript ledger. Each active hoard is a
 * stanza with a gilt-filling drop-cap (IlluminatedVersal). Each completed
 * hoard is a legendary wax seal (CompletedHoardSeal). The page opens with
 * an IncipitBand hero whose drop-cap fills with the aggregate progress
 * across active hoards.
 */
export default function HoardsTab() {
  const { data, loading, error, reload } = useApi(getSavingsGoals);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  const { active, completed, overallPercent, metaLabel } = useMemo(() => {
    const goals = normalizeList(data);
    const a = goals.filter((g) => !g.is_completed);
    const c = goals
      .filter((g) => g.is_completed)
      .sort((x, y) => new Date(y.completed_at) - new Date(x.completed_at));

    let pct = 0;
    if (a.length > 0) {
      const sum = a.reduce((acc, g) => acc + (Number(g.percent_complete) || 0), 0);
      pct = clampPct(sum / a.length);
    } else if (c.length > 0) {
      pct = 100;
    }

    let meta;
    if (a.length === 0 && c.length === 0) {
      meta = 'Create your first goal';
    } else if (a.length === 0) {
      meta = `${c.length} ${c.length === 1 ? 'goal' : 'goals'} completed`;
    } else {
      meta = `${a.length} active ${a.length === 1 ? 'goal' : 'goals'} · ${Math.round(pct)}% average progress`;
    }

    return { active: a, completed: c, overallPercent: pct, metaLabel: meta };
  }, [data]);

  if (loading) return <Loader />;
  // Same footgun as the create sheet: children never render, so a failed
  // savings-goals fetch painted a completely blank Hoards tab.
  if (error) {
    return (
      <ErrorAlert
        message={`Couldn't load your savings goals. ${error}`}
        onRetry={reload}
      />
    );
  }

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

  const everythingEmpty = active.length === 0 && completed.length === 0;

  return (
    <div className="space-y-6">
      <IncipitBand
        letter="S"
        title="Savings goals"
        kicker="Goals for earned money still owed to you"
        meta={metaLabel}
        progressPct={overallPercent}
        versalSize="xl"
      />
      <p className="text-body text-ink-secondary">
        These goals track earned money your parent still owes you. They do not track money already in Greenlight; recording a payout reduces this goal progress.
      </p>

      <div className="flex justify-end">
        <Button
          variant="primary"
          size="sm"
          onClick={() => setSheetOpen(true)}
          aria-label="New savings goal"
        >
          <Plus size={16} /> New goal
        </Button>
      </div>

      {everythingEmpty && (
        <ParchmentCard
          variant="sealed"
          tone="bright"
          flourish
          seal="top-right"
          className="text-center py-10"
        >
          <p className="font-script text-lede text-ink-secondary">
            No savings goals yet.
          </p>
          <p className="mt-2 font-body text-body text-ink-whisper max-w-md mx-auto">
            Set a goal for something you want. Every dollar still owed to you
            counts toward it.
          </p>
        </ParchmentCard>
      )}

      {active.length > 0 && (
        <section aria-labelledby="hoards-active-rubric">
          <div id="hoards-active-rubric">
            <ChapterRubric index={0} name="Active goals" />
          </div>
          <div className="mt-3 grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {active.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                onDelete={setPendingDelete}
              />
            ))}
          </div>
        </section>
      )}

      {completed.length > 0 && (
        <section aria-labelledby="hoards-completed-rubric">
          <div id="hoards-completed-rubric">
            <ChapterRubric index={1} name="Completed goals" />
          </div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {completed.map((goal) => (
              <CompletedHoardSeal key={goal.id} goal={goal} />
            ))}
          </div>
        </section>
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
          message="This removes the savings goal. Your balance stays the same."
          confirmLabel="Remove"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
