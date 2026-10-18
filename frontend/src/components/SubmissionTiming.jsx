import { formatDate } from '../utils/format';
import TimelinessBadge from './TimelinessBadge';

function submittedTime(value, zone) {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  const options = { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric',
    minute: '2-digit', timeZoneName: 'short' };
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: zone }).format(new Date(value));
  } catch {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: 'UTC' }).format(new Date(value));
  }
}

function DateValue({ value }) {
  return value ? <time dateTime={value}>{formatDate(value)}</time> : 'Not recorded';
}

export default function SubmissionTiming({ record = {}, kind }) {
  const snapshot = record.timing_snapshot?.version === 1 ? record.timing_snapshot : null;
  const zone = snapshot?.timezone || 'UTC';
  const submittedAt = snapshot?.submitted_at || record.created_at;
  const submitted = submittedTime(submittedAt, zone);
  const reviewed = submittedTime(record.decided_at, zone);
  const timeliness = snapshot ? snapshot.timeliness : record.timeliness;
  // A recurring deadline belongs to its saved period. The definition's
  // optional one-time deadline cannot describe a later weekly/daily cycle.
  const hasEditableDeadline = kind !== 'chore' || !snapshot || snapshot.schedule === 'one_time';
  const showCurrentDue = hasEditableDeadline && record.current_due_date !== undefined
    && (!snapshot || record.current_due_date !== snapshot.due_on);
  const reviewLabel = record.status === 'approved' ? 'Approved' : record.status === 'rejected' ? 'Rejected' : 'Reviewed';
  return <div className="space-y-1 font-body text-caption text-ink-secondary min-w-0">
    <dl className="space-y-1 break-words [overflow-wrap:anywhere]">
      {snapshot?.schedule === 'weekly' && <div>
        <dt className="inline font-semibold">Scheduled week</dt>{' '}
        <dd className="inline"><DateValue value={snapshot.period_start} /> – <DateValue value={snapshot.period_end} /></dd>
      </div>}
      {snapshot?.schedule === 'daily' && <div>
        <dt className="inline font-semibold">Scheduled for</dt>{' '}
        <dd className="inline"><DateValue value={snapshot.period_start} /></dd>
      </div>}
      {!snapshot && record.completed_date && <div>
        <dt className="inline font-semibold">Recorded period date</dt>{' '}
        <dd className="inline"><DateValue value={record.completed_date} /></dd>
      </div>}
      <div>
        <dt className="inline font-semibold">Due</dt>{' '}
        <dd className="inline">{snapshot ? snapshot.due_on ? <DateValue value={snapshot.due_on} /> : 'No due date' : 'Not saved for this submission'}</dd>
      </div>
      {showCurrentDue && <div>
        <dt className="inline font-semibold">Current due</dt>{' '}
        <dd className="inline">{record.current_due_date ? <DateValue value={record.current_due_date} /> : 'No due date'}</dd>
      </div>}
      <div>
        <dt className="inline font-semibold">{kind === 'chore' ? 'Marked complete' : 'Submitted'}</dt>{' '}
        <dd className="inline">{submitted ? <time dateTime={submittedAt}>{submitted}</time> : 'Not recorded'}</dd>
      </div>
      {record.decided_at && <div>
        <dt className="inline font-semibold">{reviewLabel}</dt>{' '}
        <dd className="inline">{reviewed ? <time dateTime={record.decided_at}>{reviewed}</time> : 'Not recorded'}</dd>
      </div>}
    </dl>
    {(!snapshot || snapshot.due_on) && <p>{!snapshot && timeliness && 'Recorded timing: '}<TimelinessBadge timeliness={timeliness} /></p>}
    {!snapshot && <p className="text-ink-whisper">The original deadline and schedule were not saved for this older submission.</p>}
  </div>;
}
