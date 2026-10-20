import { useCallback, useEffect, useRef, useState } from 'react';
import * as Sentry from '@sentry/react';
import { getPulse } from '../api';
import { useAuth } from '../hooks/useApi';
import { PulseContext, PULSE_INTERVAL_MS, PULSE_OUTAGE_REPORT_BEATS } from './pulseContext';
import { getToken, GATEWAY_STATUSES } from '../api/client';

/**
 * PulseProvider — the shell's single background poller.
 *
 * Every toast stack, the notification bell, the header pips, and the
 * first-encounter check used to run their own `setInterval` against their own
 * endpoint — roughly 21 requests a minute for a signed-in child. This polls
 * `/api/pulse/` once and hands each consumer its slice; the hooks keep their
 * own diffing/dedupe logic and only changed transport.
 *
 * Skips beats while the tab is hidden (a backgrounded phone shouldn't burn
 * battery or data) and catches up immediately on `visibilitychange` — the
 * pattern useDropToasts established and three of the old pollers lacked.
 *
 * A deploy briefly leaves the proxy answering 502/503/504 to a poller that is
 * still running in every open tab, so the API client leaves those statuses to
 * this provider: they are reported to Sentry once they span
 * PULSE_OUTAGE_REPORT_BEATS beats in a row, not for each tab's one missed beat.
 */
export function PulseProvider({ children, intervalMs = PULSE_INTERVAL_MS }) {
  const { user } = useAuth();
  const account = user ? `${user.id}:${getToken()}` : null;
  const accountRef = useRef(account);
  useEffect(() => { accountRef.current = account; }, [account]);
  const [savedPulse, setSavedPulse] = useState(null);
  const pulse = savedPulse?.account === account ? savedPulse.data : null;
  const cancelledRef = useRef(false);
  const gatewayFailuresRef = useRef(0);

  const beat = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    const requestedAccount = accountRef.current;
    if (!requestedAccount) return;
    try {
      const data = await getPulse();
      gatewayFailuresRef.current = 0;
      if (!cancelledRef.current && accountRef.current === requestedAccount) setSavedPulse({ account: requestedAccount, data });
    } catch (err) {
      // Otherwise silent, like every poller before it — a missed beat must
      // never break the shell, and the next one is 30s away.
      if (GATEWAY_STATUSES.includes(err?.status)) {
        gatewayFailuresRef.current += 1;
        // Exactly once per outage; the count restarts after a good beat.
        if (gatewayFailuresRef.current === PULSE_OUTAGE_REPORT_BEATS) {
          Sentry.captureException(
            new Error(`API ${err.status}: GET /pulse/ (${PULSE_OUTAGE_REPORT_BEATS} consecutive beats)`),
            { extra: { status: err.status, beats: PULSE_OUTAGE_REPORT_BEATS } },
          );
        }
      }
    }
  }, []);

  useEffect(() => {
    if (!user) {
      return undefined;
    }
    cancelledRef.current = false;
    beat();
    const interval = setInterval(beat, intervalMs);
    const onVisibility = () => {
      if (typeof document !== 'undefined' && !document.hidden) beat();
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibility);
    }
    return () => {
      cancelledRef.current = true;
      clearInterval(interval);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, [user, account, intervalMs, beat]);

  return (
    <PulseContext.Provider value={{ pulse, refresh: beat }}>
      {children}
    </PulseContext.Provider>
  );
}
