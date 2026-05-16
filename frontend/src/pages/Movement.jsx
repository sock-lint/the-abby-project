import { useMemo, useState } from 'react';
import { Plus, Trash2, Activity } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import {
  listMovementSessions, deleteMovementSession,
} from '../api';
import { normalizeList } from '../utils/api';
import { toISODate } from '../utils/dates';
import { formatDateTime } from '../utils/format';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import IconButton from '../components/IconButton';
import ConfirmDialog from '../components/ConfirmDialog';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import ChapterRubric from '../components/atlas/ChapterRubric';
import MovementSessionLogModal from '../components/MovementSessionLogModal';
import QuestFolio from './quests/QuestFolio';

const INTENSITY_TONE = { low: 'moss', medium: 'teal', high: 'ember' };

function SessionRow({ session, canDelete, onDelete }) {
  return (
    <ParchmentCard className="flex items-center gap-3">
      <div className="text-2xl shrink-0" aria-hidden>
        {session.movement_type_icon || '🏃'}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-display text-base text-ink-primary leading-tight">
          {session.movement_type_name}
        </div>
        <div className="font-script text-xs text-ink-whisper">
          {formatDateTime(session.created_at)} · {session.duration_minutes} min
          {session.xp_awarded > 0 && (
            <span className="text-moss-deep"> · +{session.xp_awarded} XP</span>
          )}
        </div>
        {session.notes && (
          <div className="font-body text-xs text-ink-secondary italic truncate mt-0.5">
            {session.notes}
          </div>
        )}
      </div>
      <RuneBadge tone={INTENSITY_TONE[session.intensity] || 'ink'} size="sm">
        {session.intensity}
      </RuneBadge>
      {canDelete && (
        <IconButton
          aria-label={`Remove ${session.movement_type_name} session`}
          onClick={() => onDelete(session)}
          className="shrink-0"
        >
          <Trash2 size={16} />
        </IconButton>
      )}
    </ParchmentCard>
  );
}

export default function Movement() {
  const { user, isParent } = useRole();
  const { data, loading, reload, error } = useApi(listMovementSessions);
  const [logOpen, setLogOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const sessions = normalizeList(data);
  const today = toISODate(new Date());

  const { todays, earlier } = useMemo(() => {
    const t = [];
    const e = [];
    for (const s of sessions) {
      (s.occurred_on === today ? t : e).push(s);
    }
    return { todays: t, earlier: e.slice(0, 20) };
  }, [sessions, today]);

  const handleDelete = async () => {
    if (!pendingDelete) return;
    setBusy(true);
    setActionError('');
    try {
      await deleteMovementSession(pendingDelete.id);
      setPendingDelete(null);
      reload();
    } catch (err) {
      setActionError(err?.message || 'Could not remove that session.');
    } finally {
      setBusy(false);
    }
  };

  const canDelete = (session) =>
    isParent || session.user === user?.id;

  if (loading) return <Loader />;

  // Verso math — "first 3 a day fire bonus XP" is the natural progression
  // target. Cap progressPct at 100% once the daily bonus slots are used.
  const dailyTarget = 3;
  const versoProgressPct = Math.min(100, (todays.length / dailyTarget) * 100);
  const versoProgressLabel = todays.length === 0
    ? 'first 3 each day fire bonus XP'
    : `${Math.min(todays.length, dailyTarget)} of ${dailyTarget} bonus slots used`;

  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="M"
        title="Movement"
        kicker="sessions, practices, runs"
        meta="duration × intensity feeds your Physical skills"
        stats={[
          { value: todays.length, label: 'today' },
          { value: sessions.length, label: 'all-time' },
        ]}
        progressPct={versoProgressPct}
        progressLabel={versoProgressLabel}
      >
        <ErrorAlert message={error?.message || actionError} />

        {!isParent && (
          <div className="flex justify-end">
            <Button
              onClick={() => setLogOpen(true)}
              className="flex items-center gap-1 shrink-0"
            >
              <Plus size={16} /> Log
            </Button>
          </div>
        )}

        <section>
          <ChapterRubric index={nextRubric()} name="Today" />
          {todays.length === 0 ? (
            <EmptyState icon={<Activity size={28} />}>
              Nothing logged yet today. Tap “Log” after a workout, practice, or run.
            </EmptyState>
          ) : (
            <div className="space-y-2">
              {todays.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  canDelete={canDelete(s)}
                  onDelete={setPendingDelete}
                />
              ))}
            </div>
          )}
        </section>

        {earlier.length > 0 && (
          <section>
            <ChapterRubric index={nextRubric()} name="Earlier" />
            <div className="space-y-2">
              {earlier.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  canDelete={canDelete(s)}
                  onDelete={setPendingDelete}
                />
              ))}
            </div>
          </section>
        )}
      </QuestFolio>

      {logOpen && (
        <MovementSessionLogModal
          onClose={() => setLogOpen(false)}
          onSaved={() => {
            setLogOpen(false);
            reload();
          }}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Remove this session?"
          message={`This won't restore the daily-bonus slot it used.`}
          confirmLabel={busy ? 'Removing…' : 'Remove'}
          onConfirm={handleDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
