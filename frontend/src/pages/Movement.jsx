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
import MovementSessionLogModal from '../components/MovementSessionLogModal';

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

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            movement · sessions, practices, runs
          </div>
          <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
            Movement
          </h2>
          <div className="font-script text-xs text-ink-whisper mt-1">
            Log what you did. Duration × intensity feeds your Physical skills;
            the first 3 each day fire bonus XP and drops.
          </div>
        </div>
        {!isParent && (
          <Button
            onClick={() => setLogOpen(true)}
            className="flex items-center gap-1 shrink-0"
          >
            <Plus size={16} /> Log
          </Button>
        )}
      </header>

      <ErrorAlert message={error?.message || actionError} />

      <section aria-labelledby="movement-today">
        <h3 id="movement-today" className="font-display text-lg text-ink-primary mb-2">
          Today
        </h3>
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
        <section aria-labelledby="movement-earlier">
          <h3 id="movement-earlier" className="font-display text-lg text-ink-primary mb-2">
            Earlier
          </h3>
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
