import { useEffect, useRef, useState } from 'react';
import { Printer, Wifi, WifiOff } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import ProgressBar from '../../components/ProgressBar';
import ErrorAlert from '../../components/ErrorAlert';
import { getPrinterStatus } from '../../api';
import { formatDateTime } from '../../utils/format';
import {
  EVENT_TONE, JOB_STATE_TONE, SEVERITY_TONE, formatMinutes, isJobOpen,
} from './forge.constants';

/** Poll fast enough to feel live while a plate is running… */
const ACTIVE_POLL_MS = 10000;
/** …and back off hard when the bed is empty. */
const IDLE_POLL_MS = 45000;

/**
 * PrinterStatus — the live view, served entirely from our own fan-out cache.
 *
 * It polls `GET /api/printers/<id>/status/` rather than opening its own MQTT
 * connection, and that is not an implementation detail: the X1's embedded
 * broker tolerates about four clients total, shared with Bambu Studio, Handy
 * and Home Assistant. A connection per browser tab would exhaust that
 * instantly and start knocking the other clients off. One listener owns the
 * only connection; everything else reads the snapshot it publishes.
 *
 * Polling follows the ProjectIngest pattern — setTimeout recursion (not
 * setInterval, so a slow response can't stack requests), a ref cleared on
 * unmount, and a `document.hidden` skip so a backgrounded tab stops asking.
 */
export default function PrinterStatus({ printer }) {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');
  const timerRef = useRef(null);
  const mountedRef = useRef(true);
  const delayRef = useRef(IDLE_POLL_MS);

  const printerId = printer?.id;

  useEffect(() => {
    if (!printerId) return undefined;
    mountedRef.current = true;

    const tick = async () => {
      if (!mountedRef.current) return;
      // A hidden tab doesn't need fresh numbers; skip the fetch but keep the
      // loop alive so coming back to the tab picks straight back up.
      if (!document.hidden) {
        try {
          const data = await getPrinterStatus(printerId);
          if (!mountedRef.current) return;
          setSnapshot(data);
          setError('');
          delayRef.current = isJobOpen(data?.job) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
        } catch (err) {
          if (!mountedRef.current) return;
          setError(err?.message || 'Could not reach the printer status.');
          delayRef.current = IDLE_POLL_MS;
        }
      }
      if (!mountedRef.current) return;
      timerRef.current = setTimeout(tick, delayRef.current);
    };

    tick();
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [printerId]);

  const job = snapshot?.job;
  const live = snapshot?.live;
  const connected = Boolean(snapshot?.connected);
  const name = snapshot?.printer?.name || printer?.name || 'Printer';
  const events = job?.events || [];

  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Printer size={18} className="text-ink-whisper shrink-0" aria-hidden="true" />
          <span className="font-display text-base text-ink-primary truncate">{name}</span>
        </div>
        <RuneBadge
          tone={connected ? 'moss' : 'ink'}
          icon={connected ? <Wifi size={11} /> : <WifiOff size={11} />}
        >
          {connected ? 'Connected' : 'Offline'}
        </RuneBadge>
      </div>

      {error && <ErrorAlert message={error} />}

      {snapshot?.printer?.last_error && (
        <div className="font-script text-caption text-ember-deep">
          {snapshot.printer.last_error}
        </div>
      )}

      {job ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="font-body text-body text-ink-primary truncate">
              {job.request_title || job.subtask_name}
            </span>
            <RuneBadge tone={JOB_STATE_TONE[job.state] || 'ink'}>
              {job.state_display || job.state}
            </RuneBadge>
          </div>
          <ProgressBar
            value={Number(job.percent_complete) || 0}
            aria-label={`${name} print progress`}
          />
          <div className="font-script text-caption text-ink-whisper">
            {Math.round(Number(job.percent_complete) || 0)}%
            {job.total_layer_num > 0
              && ` · layer ${job.layer_num || 0} of ${job.total_layer_num}`}
            {job.remaining_minutes > 0
              && ` · ~${formatMinutes(job.remaining_minutes)} left`}
          </div>
          {!job.request && (
            <div className="font-script text-caption text-ember-deep">
              Not linked to a request yet.
            </div>
          )}
        </div>
      ) : (
        <div className="font-script text-caption text-ink-whisper">
          {connected
            ? `Idle${live?.gcode_state ? ` · ${live.gcode_state.toLowerCase()}` : ''}`
            : 'No live report — the listener isn’t connected to this printer.'}
        </div>
      )}

      {events.length > 0 && (
        <ol className="space-y-1.5 border-t border-ink-page-shadow/40 pt-3">
          {events.slice(-12).map((event) => (
            <li key={event.id} className="flex items-baseline gap-2">
              <RuneBadge tone={SEVERITY_TONE[event.severity] || EVENT_TONE[event.kind] || 'ink'}>
                {event.kind_display || event.kind}
              </RuneBadge>
              <span className="flex-1 min-w-0 font-body text-caption text-ink-secondary">
                {event.message}
              </span>
              <span className="font-script text-caption text-ink-whisper shrink-0">
                {formatDateTime(event.created_at)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </ParchmentCard>
  );
}
