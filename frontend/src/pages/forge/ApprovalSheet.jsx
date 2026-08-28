import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { TextAreaField, TextField } from '../../components/form';
import { approvePrintRequest, rejectPrintRequest } from '../../api';
import PlateFilenameChip from './PlateFilenameChip';
import { formatCap, formatGrams, formatMinutes } from './forge.constants';

/**
 * ApprovalSheet — the parent's decide flow.
 *
 * The grams + minutes come off the slicer, not the printer: the Bambu MQTT
 * report carries progress and layers but never consumed filament, so the
 * parent's estimate at this moment is what the monthly budget debits later.
 *
 * A 409 means "this would blow the monthly cap" and carries the specific
 * overage in `problems`. That is a guard rail, not a lock — the parent gets
 * an explicit "Approve anyway" that re-POSTs with `force: true`, because the
 * parent is the one who decides. Branching is on `err.status`, never on the
 * message text.
 */
export default function ApprovalSheet({ request, onClose, onDecided }) {
  const [grams, setGrams] = useState(
    request.estimated_grams !== null && request.estimated_grams !== undefined
      ? String(request.estimated_grams) : '',
  );
  const [minutes, setMinutes] = useState(
    request.estimated_minutes !== null && request.estimated_minutes !== undefined
      ? String(request.estimated_minutes) : '',
  );
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(null); // { problems, budget }
  const [approved, setApproved] = useState(null); // the saved request
  // Rejecting a print is final for that request, and the two buttons sit side
  // by side under a thumb. Every other reject in the app (dashboard approval
  // queue, chores) asks once more with a note field before it fires, so this
  // one does too rather than being a single irreversible tap.
  const [confirmingReject, setConfirmingReject] = useState(false);

  const numeric = (value) => {
    const trimmed = (value ?? '').toString().trim();
    if (trimmed === '') return null;
    const n = Number(trimmed);
    return Number.isNaN(n) ? null : n;
  };

  const doApprove = async (force) => {
    setBusy(true);
    setError('');
    try {
      const saved = await approvePrintRequest(request.id, {
        estimated_grams: numeric(grams),
        estimated_minutes: numeric(minutes),
        notes: notes.trim(),
        force,
      });
      setConflict(null);
      setApproved(saved);
      onDecided?.(saved);
    } catch (err) {
      if (err?.status === 409) {
        setConflict({
          problems: err.response?.problems || [],
          budget: err.response?.budget || null,
        });
      } else {
        setError(err?.message || 'Could not approve that request.');
      }
    } finally {
      setBusy(false);
    }
  };

  const doReject = async () => {
    setBusy(true);
    setError('');
    try {
      const saved = await rejectPrintRequest(request.id, notes.trim());
      onDecided?.(saved);
      onClose?.();
    } catch (err) {
      setError(err?.message || 'Could not decline that request.');
    } finally {
      setBusy(false);
    }
  };

  if (confirmingReject) {
    return (
      <BottomSheet
        title={`Reject “${request.title}”?`}
        onClose={busy ? undefined : () => setConfirmingReject(false)}
        disabled={busy}
      >
        <div className="space-y-3">
          <p className="font-body text-body text-ink-secondary">
            This closes the request. They can always ask again with a different
            model or a smaller print.
          </p>
          <TextAreaField
            id="forge-reject-notes"
            label="Note for them (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value.slice(0, 2000))}
            placeholder="e.g. too much filament this month — try after the 1st"
            rows={3}
            helpText="Shows up in their notification feed."
          />
          {error && <ErrorAlert message={error} />}
          <div className="flex gap-2 pt-1">
            <Button
              variant="secondary"
              onClick={() => setConfirmingReject(false)}
              disabled={busy}
              className="flex-1"
            >
              Keep it pending
            </Button>
            <Button
              variant="danger"
              onClick={doReject}
              loading={busy}
              className="flex-1"
            >
              {busy ? <span>Rejecting…</span> : 'Reject'}
            </Button>
          </div>
        </div>
      </BottomSheet>
    );
  }

  if (approved) {
    return (
      <BottomSheet title="Approved" onClose={onClose}>
        <div className="space-y-3">
          <p className="font-body text-body text-ink-secondary">
            {approved.title} is approved. Slice it in Bambu Studio and save the
            plate under this exact name — that is how the printer’s job finds
            its way back to the request.
          </p>
          <PlateFilenameChip filename={approved.plate_filename} />
          <Button onClick={onClose} className="w-full">Done</Button>
        </div>
      </BottomSheet>
    );
  }

  return (
    <BottomSheet title="Decide on this print" onClose={onClose}>
      <div className="space-y-3">
        <ParchmentCard tone="deep" className="!p-3 space-y-1">
          <div className="font-display text-body text-ink-primary">{request.title}</div>
          <div className="font-script text-caption text-ink-whisper">
            {request.user_name || request.username} · {request.color}
          </div>
          {request.reason && (
            <p className="font-body text-caption text-ink-secondary italic">
              “{request.reason}”
            </p>
          )}
        </ParchmentCard>

        <TextField
          id="forge-grams"
          label="Filament estimate (grams)"
          type="number"
          min="0"
          step="1"
          value={grams}
          onChange={(e) => setGrams(e.target.value)}
          helpText="From the slicer. The printer never reports filament, so this is what the budget debits."
        />

        <TextField
          id="forge-minutes"
          label="Print time estimate (minutes)"
          type="number"
          min="0"
          step="1"
          value={minutes}
          onChange={(e) => setMinutes(e.target.value)}
        />

        <TextAreaField
          id="forge-notes"
          label="Note (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 2000))}
          placeholder="Shared with them either way."
          rows={2}
        />

        {conflict && (
          <div
            role="alert"
            className="rounded-lg border border-ember/40 bg-ember/10 px-3 py-2 space-y-2"
          >
            <div className="flex items-center gap-2 font-display text-body text-ember-deep">
              <AlertTriangle size={16} aria-hidden="true" />
              Over this month’s print budget
            </div>
            <ul className="list-disc pl-5 font-body text-caption text-ember-deep space-y-0.5">
              {conflict.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
            {conflict.budget && (
              <div className="font-script text-caption text-ink-whisper">
                Used {formatGrams(conflict.budget.grams_used)} of{' '}
                {formatCap(conflict.budget.grams_per_month, 'grams')} ·{' '}
                {formatMinutes(conflict.budget.minutes_used)} of{' '}
                {formatCap(conflict.budget.minutes_per_month, 'minutes')}
              </div>
            )}
            <Button
              variant="danger"
              size="sm"
              onClick={() => doApprove(true)}
              disabled={busy}
            >
              Approve anyway
            </Button>
          </div>
        )}

        {error && <ErrorAlert message={error} />}

        <div className="flex gap-2 pt-1">
          <Button
            variant="danger"
            onClick={() => { setError(''); setConfirmingReject(true); }}
            disabled={busy}
            className="flex-1"
          >
            Reject
          </Button>
          <Button
            onClick={() => doApprove(false)}
            loading={busy}
            className="flex-1"
          >
            Approve
          </Button>
        </div>
      </div>
    </BottomSheet>
  );
}
