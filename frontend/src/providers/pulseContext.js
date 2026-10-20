import { createContext, useContext } from 'react';

// One beat every 30s. The eight timers this replaced ranged from 20s to 60s
// and together woke a phone's radio every ~7 seconds.
export const PULSE_INTERVAL_MS = 30000;

// Consecutive gateway failures (502/503/504) before the outage is reported —
// about a minute and a half, longer than a deploy's container swap.
export const PULSE_OUTAGE_REPORT_BEATS = 3;

export const PulseContext = createContext(null);

/**
 * usePulse — read the latest heartbeat. Returns `{ pulse, refresh }` with
 * `pulse` null until the first beat lands (and outside a provider, so a
 * component rendered in isolation degrades to "no signal yet" rather than
 * throwing).
 */
export function usePulse() {
  return useContext(PulseContext) || { pulse: null, refresh: () => {} };
}
