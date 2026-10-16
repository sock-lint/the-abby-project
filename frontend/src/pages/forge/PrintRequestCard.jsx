import { Box, CalendarClock, Palette } from 'lucide-react';
import { Link } from 'react-router-dom';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import StatusBadge from '../../components/StatusBadge';
import ProgressBar from '../../components/ProgressBar';
import Button from '../../components/Button';
import AddToCalendar from '../../components/AddToCalendar';
import { formatDate } from '../../utils/format';
import PlateFilenameChip from './PlateFilenameChip';
import { formatMinutes, isJobOpen, jobProgressLabel } from './forge.constants';

/**
 * PrintRequestCard — one row of the Forge.
 *
 * Four states worth reading differently:
 *   pending    — waiting on a parent; the reason is the argument.
 *   approved   — carries the minted plate filename, which is the whole
 *                point of the flow (see PlateFilenameChip).
 *   printing   — live progress from the MQTT listener.
 *   failed     — the *decoded* failure sentence, never an HMS code.
 */
export default function PrintRequestCard({
  request,
  canDecide = false,
  canCancel = false,
  canExchange = false,
  exchanging = false,
  exchangeDisabled = false,
  onDecide,
  onCancel,
  onExchange,
  showOwner = false,
  showPlateFilename = false,
}) {
  const job = request.latest_job;
  const live = isJobOpen(job);
  const failed = job && job.state === 'failed';
  const quoted = request.status === 'quoted';
  const paid = Number(request.coins_paid) > 0;
  const refunded = Number(request.coins_refunded) > 0;
  const coinLabel = (coins) => `${coins} ${Number(coins) === 1 ? 'coin' : 'coins'}`;

  return (
    <ParchmentCard className="space-y-3">
      <div className="flex gap-3">
        {request.thumbnail ? (
          <img
            src={request.thumbnail}
            alt=""
            className="w-16 h-16 rounded-lg object-cover border border-ink-page-shadow shrink-0"
          />
        ) : (
          <div
            aria-hidden="true"
            className="w-16 h-16 rounded-lg border border-ink-page-shadow bg-ink-page-shadow/40 flex items-center justify-center text-ink-whisper shrink-0"
          >
            <Box size={24} />
          </div>
        )}

        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-display text-base text-ink-primary leading-tight">
              {request.source_url ? (
                <a
                  href={request.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:underline"
                >
                  {request.title}
                </a>
              ) : (
                request.title
              )}
            </h3>
            {quoted
              ? <RuneBadge tone="gold">Awaiting coin exchange</RuneBadge>
              : <StatusBadge status={request.status} />}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {request.color && (
              <RuneBadge tone="royal" icon={<Palette size={11} />}>
                {request.color}
              </RuneBadge>
            )}
            {request.needed_by && (
              <>
                <RuneBadge tone="gold" icon={<CalendarClock size={11} />}>
                  by {formatDate(request.needed_by)}
                </RuneBadge>
                <AddToCalendar event={{
                  id: `print:${request.id}`,
                  title: `Print needed: ${request.title}`,
                  start: request.needed_by,
                  description: 'Requested print needed by this date.',
                  path: '/treasury?tab=forge',
                }} />
              </>
            )}
            {showOwner && request.user_name && (
              <span className="font-script text-caption text-ink-whisper">
                {request.user_name}
              </span>
            )}
          </div>

          {request.project != null && request.project_title && (
            <Link
              to={`/quests/ventures/${request.project}`}
              className="inline-flex min-h-11 items-center font-body text-caption text-sheikah-teal-deep hover:underline break-words"
            >
              Project: {request.project_title}
            </Link>
          )}

          {request.reason && (
            <p className="font-body text-caption text-ink-secondary italic">
              “{request.reason}”
            </p>
          )}
        </div>
      </div>

      {(quoted || paid || refunded) && (
        <div className="space-y-1 rounded-lg border border-gold-leaf/30 bg-gold-leaf/10 px-3 py-2">
          <p className="font-body text-body text-ink-primary">
            {refunded ? `Refunded ${coinLabel(request.coins_refunded)}`
              : paid ? `Exchanged ${coinLabel(request.coins_paid)}`
                : `Fixed quote: ${coinLabel(request.coin_cost)}`}
          </p>
          {request.minutes_per_coin_snapshot != null && (
            <p className="font-body text-caption text-ink-secondary">
              Estimated print time: {formatMinutes(request.estimated_minutes)} · {request.minutes_per_coin_snapshot} {Number(request.minutes_per_coin_snapshot) === 1 ? 'minute' : 'minutes'} per coin
            </p>
          )}
          {!refunded && (
            <p className="font-body text-caption text-ink-secondary">
              Retries do not cost extra coins. Cancelling before the first print job refunds exchanged coins.
            </p>
          )}
        </div>
      )}

      {showPlateFilename && request.plate_filename && !quoted && request.status !== 'rejected'
        && request.status !== 'cancelled' && (
        <PlateFilenameChip filename={request.plate_filename} />
      )}

      {live && (
        <div className="space-y-1">
          <ProgressBar
            value={Number(job.percent_complete) || 0}
            aria-label={`${request.title} print progress`}
          />
          <div className="font-script text-caption text-ink-whisper">
            {jobProgressLabel(job)}
          </div>
        </div>
      )}

      {failed && job.failure_reason && (
        <div
          role="status"
          className="rounded-lg border border-ember/40 bg-ember/10 px-3 py-2 font-body text-caption text-ember-deep"
        >
          {job.failure_reason}
        </div>
      )}

      {request.parent_notes && (
        <div className="font-script text-caption text-ink-whisper">
          Parent note: {request.parent_notes}
        </div>
      )}

      {(canDecide || canCancel || canExchange) && (
        <div className="flex flex-wrap justify-end gap-2">
          {canCancel && (
            <Button variant="ghost" size="sm" disabled={exchangeDisabled || exchanging} onClick={() => onCancel?.(request)}>
              Cancel
            </Button>
          )}
          {canExchange && quoted && (
            <Button size="sm" loading={exchanging} disabled={exchangeDisabled} onClick={() => onExchange?.(request)}>
              Exchange {coinLabel(request.coin_cost)}
            </Button>
          )}
          {canDecide && (
            <Button size="sm" onClick={() => onDecide?.(request)}>
              Decide
            </Button>
          )}
        </div>
      )}
    </ParchmentCard>
  );
}
