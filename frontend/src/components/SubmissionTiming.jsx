import { formatDate } from '../utils/format';
import TimelinessBadge from './TimelinessBadge';

function timestampInZone(value, zones, dateOnly = false) {
  if (!value || !Number.isFinite(Date.parse(value))) return null;
  const options = dateOnly ? { year: 'numeric', month: '2-digit', day: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric',
      minute: '2-digit', timeZoneName: 'short' };
  for (const zone of zones.filter(Boolean)) {
    try {
      // Internal date-only values must stay Gregorian ISO dates regardless
      // of the browser's calendar or digit shapes. Display remains localized.
      const formatter = new Intl.DateTimeFormat(dateOnly ? 'en-CA' : undefined, { ...options, timeZone: zone });
      if (!dateOnly) return formatter.format(new Date(value));
      const parts = formatter.formatToParts(new Date(value));
      const part = (type) => parts.find((item) => item.type === type).value;
      return `${part('year')}-${part('month')}-${part('day')}`;
    } catch {
      // Fall back through the household zone before using the app default.
    }
  }
  return null;
}

function DateValue({ value }) {
  return value ? <time dateTime={value}>{formatDate(value)}</time> : 'Not recorded';
}

function ChoreTiming({ record, snapshot, zones, submittedAt, submitted, reviewed, reviewLabel }) {
  // The saved local day is authoritative. A legacy period key may be Monday
  // for a weekly chore, so it cannot establish the original scheduled day.
  const doneOn = snapshot?.submitted_on || timestampInZone(submittedAt, zones, true);
  const scheduledOn = snapshot?.due_on;
  const scheduleChanged = snapshot?.schedule === 'one_time' && record.current_due_date !== undefined
    && record.current_due_date !== snapshot.due_on;
  return <div className="space-y-1 font-body text-caption text-ink-secondary min-w-0">
    <dl className="space-y-1 break-words [overflow-wrap:anywhere]">
      <div>
        <dt className="inline font-semibold">Scheduled for</dt>{' '}
        <dd className="inline">{scheduledOn ? <DateValue value={scheduledOn} /> : snapshot ? 'No scheduled date' : 'Not recorded'}</dd>
      </div>
      <div>
        <dt className="inline font-semibold">Done on</dt>{' '}
        <dd className="inline"><DateValue value={doneOn} /></dd>
      </div>
    </dl>
    <details>
      <summary className="min-h-11 cursor-pointer py-3">Completion details</summary>
      <dl className="space-y-1 break-words [overflow-wrap:anywhere]">
        {submitted && <div>
          <dt className="inline font-semibold">Marked complete</dt>{' '}
          <dd className="inline"><time dateTime={submittedAt}>{submitted}</time></dd>
        </div>}
        {record.decided_at && <div>
          <dt className="inline font-semibold">{reviewLabel}</dt>{' '}
          <dd className="inline">{reviewed ? <time dateTime={record.decided_at}>{reviewed}</time> : 'Not recorded'}</dd>
        </div>}
        {!snapshot && record.completed_date && <div>
          <dt className="inline font-semibold">Recorded for</dt>{' '}
          <dd className="inline"><DateValue value={record.completed_date} /></dd>
        </div>}
        {scheduleChanged && <div>
          <dt className="inline font-semibold">Now scheduled for</dt>{' '}
          <dd className="inline">{record.current_due_date ? <DateValue value={record.current_due_date} /> : 'No scheduled date'}</dd>
        </div>}
      </dl>
      {!snapshot && <p className="text-ink-whisper">The original schedule was not saved for this older submission. Its recorded period does not establish when it was due.</p>}
      {scheduleChanged && <p className="text-ink-whisper">The schedule changed after this submission.</p>}
    </details>
  </div>;
}

export default function SubmissionTiming({ record = {}, kind, timezone }) {
  const isChore = kind === 'chore';
  const snapshot = record.timing_snapshot?.version === 1 ? record.timing_snapshot : null;
  const zones = [snapshot?.timezone, timezone, isChore ? 'America/Phoenix' : 'UTC'];
  const submittedAt = snapshot?.submitted_at || record.created_at;
  const submitted = timestampInZone(submittedAt, zones);
  const reviewed = timestampInZone(record.decided_at, zones);
  const reviewLabel = record.status === 'approved' ? 'Approved' : record.status === 'rejected' ? 'Rejected' : 'Reviewed';
  if (isChore) return <ChoreTiming {...{ record, snapshot, zones, submittedAt, submitted, reviewed, reviewLabel }} />;

  const timeliness = snapshot ? snapshot.timeliness : record.timeliness;
  const showCurrentDue = record.current_due_date !== undefined
    && (!snapshot || record.current_due_date !== snapshot.due_on);
  return <div className="space-y-1 font-body text-caption text-ink-secondary min-w-0">
    <dl className="space-y-1 break-words [overflow-wrap:anywhere]">
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
        <dt className="inline font-semibold">Submitted</dt>{' '}
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
