import { useCallback, useEffect, useRef, useState } from 'react';
import * as Sentry from '@sentry/react';
import { getPulse } from '../api';
import { useAuth } from '../hooks/useApi';
import { PulseContext, PULSE_INTERVAL_MS, PULSE_OUTAGE_BEATS } from './pulseContext';
import { getToken } from '../api/client';

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
 */
export function PulseProvider({ children, intervalMs = PULSE_INTERVAL_MS }) {
  const { user } = useAuth();
  const account = user ? `${user.id}:${getToken()}` : null;
  const accountRef = useRef(account);
  useEffect(() => { accountRef.current = account; }, [account]);
  const [savedPulse, setSavedPulse] = useState(null);
  const pulse = savedPulse?.account === account ? savedPulse.data : null;
  const cancelledRef = useRef(false);
  // The current run of beats the proxy answered with a gateway status or an
  // HTML page: how many, when the first and latest began, and whether it has
  // been reported. `beat` also runs from `refresh()` and on tab focus, so a
  // count alone says nothing about how long the outage has lasted.
  const failureRunRef = useRef(null);

  const beat = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    const requestedAccount = accountRef.current;
    if (!requestedAccount) return;
    const beganAt = Date.now();
    try {
      const data = await getPulse();
      if (!cancelledRef.current && accountRef.current === requestedAccount) {
        // A late answer for a previous account must not reset this one's run.
        failureRunRef.current = null;
        setSavedPulse({ account: requestedAccount, data });
      }
    } catch (err) {
      // Silent, like every poller before it — a missed beat must never break
      // the shell, and the next one is 30s away. A deploy swaps containers for
      // longer than one beat's retry, so a transient failure is reported only
      // when it persists across several beats over a real stretch of time,
      // i.e. a real outage.
      if (err?.deferredReport && accountRef.current === requestedAccount) {
        let run = failureRunRef.current;
        // Beats skipped while the tab was hidden leave a gap; failures on
        // either side of it are not one continuous outage.
        if (!run || beganAt - run.lastBeganAt > 2 * intervalMs) {
          run = { count: 0, firstBeganAt: beganAt, lastBeganAt: beganAt, reported: false };
        }
        run.count += 1;
        run.lastBeganAt = beganAt;
        failureRunRef.current = run;
        const spanMs = beganAt - run.firstBeganAt;
        if (!run.reported && run.count >= PULSE_OUTAGE_BEATS && spanMs >= (PULSE_OUTAGE_BEATS - 1) * intervalMs) {
          run.reported = true;
          Sentry.captureException(err.deferredReport.error, {
            extra: { ...err.deferredReport.extra, consecutiveFailedBeats: run.count, failingForMs: spanMs },
          });
        }
      }
    }
  }, [intervalMs]);

  useEffect(() => {
    if (!user) {
      return undefined;
    }
    cancelledRef.current = false;
    failureRunRef.current = null;
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
