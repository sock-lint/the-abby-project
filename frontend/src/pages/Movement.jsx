import { useMemo, useState } from 'react';
import { Plus, Trash2, Activity } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import { useSpace } from '../hooks/useSpace';
import {
  listMovementSessions, deleteMovementSession,
} from '../api';
import { normalizeList } from '../utils/api';
import { toISODate } from '../utils/dates';
import { formatDateTime, formatDuration } from '../utils/format';
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

function familyDay(timezone) {
  const now = new Date();
  if (!timezone) return toISODate(now);
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(now);
    const value = (name) => parts.find((part) => part.type === name).value;
    return `${value('year')}-${value('month')}-${value('day')}`;
  } catch {
    // Older cached identities may omit the family zone. Keep the UI usable
    // without changing the stored occurred_on date or granting eligibility.
    return toISODate(now);
  }
}

function SessionRow({ session, canDelete, onDelete, showOwner }) {
  return (
    <ParchmentCard className="flex items-start gap-3">
      <div className="text-2xl shrink-0" aria-hidden>
        {session.movement_type_icon || '🏃'}
      </div>
      <div className="flex-1 min-w-0">
        {showOwner && session.user_display && <div className="font-body font-semibold text-caption text-ink-secondary break-words">{session.user_display}</div>}
        <div className="font-display text-base text-ink-primary leading-tight break-words">
          {session.movement_type_name}
        </div>
        <div className="font-script text-caption text-ink-whisper">
          {formatDateTime(session.created_at)} · {formatDuration(session.duration_minutes)}
          {session.xp_awarded > 0 && (
            <span className="text-moss-deep"> · +{session.xp_awarded} XP</span>
          )}
        </div>
        {session.notes && (
          <div className="font-body text-caption text-ink-secondary italic whitespace-pre-wrap break-words [overflow-wrap:anywhere] mt-0.5">
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
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useRole();
  const { isFamilySpace: isParent } = useSpace();
  const { data, loading, refreshing, reload, error } = useApi(listMovementSessions);
  const [logOpen, setLogOpen] = useState(() => searchParams.get('log') === '1');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const closeLog = () => {
    setLogOpen(false);
    if (searchParams.has('log')) {
      const next = new URLSearchParams(searchParams);
      next.delete('log');
      next.delete('movement_type');
      next.delete('movement_type_id');
      setSearchParams(next, { replace: true });
    }
  };

  const sessions = normalizeList(data);
  const today = familyDay(user?.family?.timezone);

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

  // Saved rows prove recording and their actual XP, not how many daily award
  // slots remain: short sessions can earn zero and deletion retains the cap.
  const todayXp = todays.reduce((total, session) => total + (Number(session.xp_awarded) > 0 ? Number(session.xp_awarded) : 0), 0);

  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="M"
        title="Movement"
        kicker="Track your physical activity"
        meta="Session length and intensity determine your skill XP."
        stats={[
          { value: data === null ? '—' : todays.length, label: 'recorded today' },
          { value: data === null ? '—' : todayXp, label: 'XP earned today' },
          { value: data === null ? '—' : sessions.length, label: 'loaded sessions' },
        ]}
      >
        {/* useApi stores `error` as the message string, so `error?.message`
            was always undefined and a failed fetch rendered nothing — the page
            fell through to its empty verso as if there were no sessions. */}
        <ErrorAlert message={error} onRetry={reload} />
        <ErrorAlert message={actionError} />
        {refreshing && <p role="status" className="text-caption text-ink-secondary">Updating activity…</p>}
        {data !== null && <p className="font-body text-body text-ink-secondary">{todays.length} session{todays.length === 1 ? '' : 's'} recorded today · {todayXp} XP earned</p>}
        {!isParent && <p className="font-body text-caption text-ink-secondary">Up to 3 sessions each day can earn movement XP. Additional sessions still count toward matching goals.</p>}

        {!isParent && (
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => setLogOpen(true)}
              className="flex items-center gap-1 shrink-0"
            >
              <Plus size={16} /> Log
            </Button>
          </div>
        )}

        <section>
          <ChapterRubric index={nextRubric()} name="Today" />
          {data === null ? null : todays.length === 0 ? (
            <EmptyState icon={<Activity size={28} />}>
              No activity logged today. Add a session after a workout, practice, or run.
            </EmptyState>
          ) : (
            <div className="space-y-2">
              {todays.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  showOwner={isParent}
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
                  showOwner={isParent}
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
          initialMovementTypeId={searchParams.get('movement_type') || searchParams.get('movement_type_id') || ''}
          onClose={closeLog}
          onSaved={() => {
            closeLog();
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
