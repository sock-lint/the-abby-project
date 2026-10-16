import { useEffect, useRef } from 'react';
import { isJobOpen, OPEN_REQUEST_STATUSES } from './forge.constants';

const ACTIVE_POLL_MS = 10000;
const IDLE_POLL_MS = 45000;

// The owning page loads its initial data and presents source errors. This
// keeps the saved request cards current without exposing the hardware panel.
export default function usePrintRequestRefresh({ requests = [], reload, paused = false }) {
  const inFlightRef = useRef(null);
  const hasOpenRequests = requests.some((request) => OPEN_REQUEST_STATUSES.includes(request.status));
  const delay = requests.some((request) => request.status === 'printing' || isJobOpen(request.latest_job))
    ? ACTIVE_POLL_MS : IDLE_POLL_MS;

  useEffect(() => {
    if (paused || !hasOpenRequests) return undefined;
    let disposed = false;
    let timer;

    const schedule = () => {
      if (!disposed) timer = setTimeout(tick, delay);
    };

    const tick = async () => {
      if (disposed) return;
      if (document.hidden) {
        schedule();
        return;
      }
      // A new callback or cadence can replace this effect while its previous
      // read is unfinished. Share that promise across effect lifetimes too.
      if (inFlightRef.current) {
        await inFlightRef.current;
        schedule();
        return;
      }
      const pending = (async () => {
        try {
          await reload();
        } catch {
          // useApi owns the readable source error. A rejected custom reload
          // must still allow a later bounded refresh to detect recovery.
        }
      })();
      inFlightRef.current = pending;
      await pending;
      if (inFlightRef.current === pending) inFlightRef.current = null;
      schedule();
    };

    schedule();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [delay, hasOpenRequests, paused, reload]);
}
