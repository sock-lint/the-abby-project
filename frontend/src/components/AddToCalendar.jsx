import { useState } from 'react';
import { CalendarPlus, Download, ExternalLink } from 'lucide-react';
import Button from './Button';
import BottomSheet from './BottomSheet';
import ErrorAlert from './ErrorAlert';
import { TextField } from './form';
import { buildGoogleCalendarUrl, downloadCalendarFile } from '../utils/calendar';
import { formatDate, formatDateTime } from '../utils/format';

/** One-time provider copies of a server-confirmed date. Duties can choose
 * a single reminder day with dateEditable and their schedule's validateDate.
 */
export default function AddToCalendar({ event, className = '', size = 'sm', variant = 'ghost', dateEditable = false, dateHelp, validateDate }) {
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState(null);
  const [downloadError, setDownloadError] = useState('');
  const canEditDate = dateEditable && /^\d{4}-\d{2}-\d{2}$/.test(event?.start || '');
  const selectedDate = selection && selection.id === event?.id ? selection.date : event?.start;
  const selectedEvent = canEditDate ? { ...event, id: `${event.id}:${selectedDate}`, start: selectedDate, end: undefined } : event;
  const googleUrl = buildGoogleCalendarUrl(selectedEvent);
  const dateError = canEditDate ? (!googleUrl ? 'Choose a valid reminder date.' : validateDate?.(selectedDate)) : '';
  if (!buildGoogleCalendarUrl(event)) return null;

  function download(e) {
    e.stopPropagation();
    if (dateError) return;
    try {
      downloadCalendarFile(selectedEvent);
      setDownloadError('');
    } catch {
      setDownloadError('The calendar download could not start. Please try again.');
    }
  }

  return (
    <>
      <Button
        variant={variant}
        size={size}
        className={`inline-flex items-center gap-2 ${className}`}
        aria-label={`Add ${event.title} to calendar`}
        aria-haspopup="dialog"
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
      >
        <CalendarPlus size={16} aria-hidden="true" />
        Add to calendar
      </Button>
      {open && (
        <BottomSheet title="Add to calendar" onClose={() => setOpen(false)}>
          <p className="font-semibold text-ink-primary break-words">{event.title}</p>
          {canEditDate && (
            <TextField
              label="Reminder date"
              type="date"
              value={selectedDate}
              onChange={(e) => setSelection({ id: event.id, date: e.target.value })}
              helpText={dateHelp}
              error={dateError}
            />
          )}
          {!canEditDate && (
            <p className="text-body text-ink-secondary">
              {/^\d{4}-\d{2}-\d{2}$/.test(event.start) ? `${formatDate(event.start)} · All day` : formatDateTime(event.start)}
            </p>
          )}
          <p className="text-body text-ink-secondary">This adds a one-time copy. If the date changes here, update your calendar copy.</p>
          <div className="flex flex-col gap-3">
            <a
              role="link"
              href={dateError ? undefined : googleUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-disabled={dateError ? true : undefined}
              tabIndex={dateError ? -1 : undefined}
              onClick={(e) => { e.stopPropagation(); if (dateError) e.preventDefault(); }}
              className={`inline-flex min-h-11 items-center gap-2 text-sheikah-teal-deep underline underline-offset-4${dateError ? ' opacity-50' : ''}`}
            >
              <ExternalLink size={16} aria-hidden="true" />
              Google Calendar
            </a>
            <Button variant="secondary" disabled={Boolean(dateError)} onClick={download} className="inline-flex items-center justify-center gap-2">
              <Download size={16} aria-hidden="true" />
              Apple Calendar (.ics)
            </Button>
          </div>
          <p className="text-caption text-ink-secondary">For Apple Calendar, download the .ics file, then open or import it in Calendar on your Mac. Other calendar apps can import it too.</p>
          {downloadError && <ErrorAlert message={downloadError} />}
        </BottomSheet>
      )}
    </>
  );
}
