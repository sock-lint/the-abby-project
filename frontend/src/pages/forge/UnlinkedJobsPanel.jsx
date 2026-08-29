import { useState } from 'react';
import { EyeOff, RotateCcw, Trash2, Unlink } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import ConfirmDialog from '../../components/ConfirmDialog';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import {
  deletePrintJob, dismissPrintJob, linkPrintJob, restorePrintJob,
} from '../../api';
import { formatDateTime } from '../../utils/format';
import { JOB_STATE_TONE, LINKABLE_REQUEST_STATUSES } from './forge.constants';

/**
 * UnlinkedJobsPanel — the Handy escape hatch, parent-only.
 *
 * Everything else in this feature is deterministic: the app mints
 * `req-0042-dragon`, the parent saves the plate under that name, and the
 * listener matches the printer's reported `subtask_name` by exact equality.
 * This panel exists for the one case that breaks — a plate started from
 * Handy in a hurry, where nobody renamed anything. It is the only
 * non-deterministic path in the system, which is why it is a deliberate
 * parent action rather than a fuzzy auto-match.
 *
 * It also has to be *emptyable*. Every print a parent runs for themselves
 * lands here and matches nothing, so with only a Link action the list grows
 * forever and stops reading as a queue. Two ways out:
 *
 * - **Dismiss** hides the row and keeps everything — the job, its timeline,
 *   its place in the printer's history. Reversible from "Show cleared", which
 *   is the whole reason to prefer it; a dismiss nobody can undo is just a
 *   delete that lies about it.
 * - **Delete** removes the job and its timeline for good, behind a
 *   ConfirmDialog because nothing brings it back.
 *
 * The server refuses both on a print that is still running or one linked to a
 * request, so the destructive path can never take a live job or a child's
 * record with it.
 */
export default function UnlinkedJobsPanel({
  jobs, dismissedJobs = [], requests, onLinked, onChanged,
}) {
  const [picking, setPicking] = useState(null); // the job being linked
  const [confirming, setConfirming] = useState(null); // the job being deleted
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showCleared, setShowCleared] = useState(false);

  const candidates = (requests || []).filter(
    (request) => LINKABLE_REQUEST_STATUSES.includes(request.status),
  );

  const link = async (requestId) => {
    setBusy(true);
    setError('');
    try {
      await linkPrintJob(picking.id, requestId);
      setPicking(null);
      onLinked?.();
    } catch (err) {
      setError(err?.message || 'Could not link that print.');
    } finally {
      setBusy(false);
    }
  };

  /** One wrapper for all three: same busy flag, same error surface. */
  const run = async (action, job, failureText) => {
    setBusy(true);
    setError('');
    try {
      await action(job.id);
      onChanged?.();
    } catch (err) {
      setError(err?.message || failureText);
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    const job = confirming;
    setConfirming(null);
    await run(deletePrintJob, job, 'Could not delete that print.');
  };

  const renderCard = (job, { cleared = false } = {}) => (
    <ParchmentCard key={job.id} className="space-y-2">
      <div className="min-w-0">
        <div className="font-body text-body text-ink-primary truncate">
          {job.subtask_name || 'Unnamed plate'}
        </div>
        <div className="font-script text-caption text-ink-whisper">
          {job.printer_name} · {formatDateTime(job.started_at)}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <RuneBadge tone={JOB_STATE_TONE[job.state] || 'ink'}>
          {job.state_display || job.state}
        </RuneBadge>
        <div className="flex-1" />
        {cleared ? (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => run(restorePrintJob, job, 'Could not restore that print.')}
          >
            <RotateCcw size={14} aria-hidden="true" /> Restore
          </Button>
        ) : (
          <>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => { setError(''); setPicking(job); }}
            >
              Link to request
            </Button>
            <IconButton
              aria-label={`Dismiss ${job.subtask_name || 'this print'}`}
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => run(dismissPrintJob, job, 'Could not dismiss that print.')}
            >
              <EyeOff size={16} />
            </IconButton>
            <IconButton
              aria-label={`Delete ${job.subtask_name || 'this print'}`}
              variant="danger"
              size="sm"
              disabled={busy}
              onClick={() => { setError(''); setConfirming(job); }}
            >
              <Trash2 size={16} />
            </IconButton>
          </>
        )}
      </div>
    </ParchmentCard>
  );

  const clearedCount = dismissedJobs.length;
  const nothingToShow = (!jobs || jobs.length === 0);

  return (
    <div className="space-y-3">
      <ErrorAlert message={error} />

      {nothingToShow ? (
        <EmptyState icon={<Unlink size={24} />}>
          Every print the printer reported found its request. Nothing to link.
        </EmptyState>
      ) : (
        jobs.map((job) => renderCard(job))
      )}

      {clearedCount > 0 && (
        <div className="space-y-2">
          <button
            type="button"
            className="font-script text-caption text-ink-whisper underline"
            onClick={() => setShowCleared((open) => !open)}
          >
            {showCleared
              ? 'Hide cleared prints'
              : `Show ${clearedCount} cleared print${clearedCount === 1 ? '' : 's'}`}
          </button>
          {showCleared && dismissedJobs.map((job) => renderCard(job, { cleared: true }))}
        </div>
      )}

      {picking && (
        <BottomSheet title="Link this print" onClose={() => setPicking(null)}>
          <div className="space-y-3">
            <p className="font-script text-caption text-ink-whisper">
              “{picking.subtask_name}” on {picking.printer_name}
            </p>
            {candidates.length === 0 ? (
              <p className="font-body text-body text-ink-secondary">
                No approved requests to link this to yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {candidates.map((request) => (
                  <li key={request.id}>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busy}
                      onClick={() => link(request.id)}
                      className="w-full text-left"
                    >
                      {request.title}
                      <span className="font-script text-ink-whisper">
                        {' '}· {request.user_name || request.username}
                      </span>
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <ErrorAlert message={error} />
          </div>
        </BottomSheet>
      )}

      {confirming && (
        <ConfirmDialog
          title="Delete this print?"
          message={
            `“${confirming.subtask_name || 'Unnamed plate'}” and its timeline go `
            + 'for good. Dismiss instead if you only want it out of the way.'
          }
          confirmLabel="Delete"
          onConfirm={confirmDelete}
          onCancel={() => setConfirming(null)}
        />
      )}
    </div>
  );
}
