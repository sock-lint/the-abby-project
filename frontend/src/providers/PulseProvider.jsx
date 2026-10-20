import { useCallback, useEffect, useRef, useState } from 'react';
import { getPulse } from '../api';
import { useAuth } from '../hooks/useApi';
import { PulseContext, PULSE_INTERVAL_MS } from './pulseContext';
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

  const beat = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    const requestedAccount = accountRef.current;
    if (!requestedAccount) return;
    try {
      const data = await getPulse();
      if (!cancelledRef.current && accountRef.current === requestedAccount) setSavedPulse({ account: requestedAccount, data });
    } catch {
      // Silent, like every poller before it — a missed beat must never break
      // the shell, and the next one is 30s away.
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
