import { useState } from 'react';
import { Unlink } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import { linkPrintJob } from '../../api';
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
 */
export default function UnlinkedJobsPanel({ jobs, requests, onLinked }) {
  const [picking, setPicking] = useState(null); // the job being linked
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

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

  if (!jobs || jobs.length === 0) {
    return (
      <EmptyState icon={<Unlink size={24} />}>
        Every print the printer reported found its request. Nothing to link.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-3">
      <ErrorAlert message={error} />
      {jobs.map((job) => (
        <ParchmentCard key={job.id} className="flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="font-body text-body text-ink-primary truncate">
              {job.subtask_name || 'Unnamed plate'}
            </div>
            <div className="font-script text-caption text-ink-whisper">
              {job.printer_name} · {formatDateTime(job.started_at)}
            </div>
          </div>
          <RuneBadge tone={JOB_STATE_TONE[job.state] || 'ink'}>
            {job.state_display || job.state}
          </RuneBadge>
          <Button size="sm" onClick={() => { setError(''); setPicking(job); }}>
            Link to request
          </Button>
        </ParchmentCard>
      ))}

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
    </div>
  );
}
