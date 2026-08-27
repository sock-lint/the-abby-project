import { Box, CalendarClock, Palette } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import StatusBadge from '../../components/StatusBadge';
import ProgressBar from '../../components/ProgressBar';
import Button from '../../components/Button';
import { formatDate } from '../../utils/format';
import PlateFilenameChip from './PlateFilenameChip';
import { isJobOpen, jobProgressLabel } from './forge.constants';

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
  onDecide,
  onCancel,
  showOwner = false,
}) {
  const job = request.latest_job;
  const live = isJobOpen(job);
  const failed = job && job.state === 'failed';

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
            <StatusBadge status={request.status} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {request.color && (
              <RuneBadge tone="royal" icon={<Palette size={11} />}>
                {request.color}
              </RuneBadge>
            )}
            {request.needed_by && (
              <RuneBadge tone="gold" icon={<CalendarClock size={11} />}>
                by {formatDate(request.needed_by)}
              </RuneBadge>
            )}
            {showOwner && request.user_name && (
              <span className="font-script text-caption text-ink-whisper">
                {request.user_name}
              </span>
            )}
          </div>

          {request.reason && (
            <p className="font-body text-caption text-ink-secondary italic">
              “{request.reason}”
            </p>
          )}
        </div>
      </div>

      {request.plate_filename && request.status !== 'rejected'
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

      {(canDecide || canCancel) && (
        <div className="flex justify-end gap-2">
          {canCancel && (
            <Button variant="ghost" size="sm" onClick={() => onCancel?.(request)}>
              Cancel
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
