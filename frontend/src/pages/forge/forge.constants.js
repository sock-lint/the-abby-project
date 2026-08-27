// Shared, non-component exports for the Forge tab. Lives in a .js sibling
// because `react-refresh/only-export-components` forbids non-component
// exports from a .jsx file (see frontend/CLAUDE.md, "Per-area shared
// constants").

/** Request statuses that still expect a print to happen. */
export const OPEN_REQUEST_STATUSES = ['pending', 'approved', 'printing', 'failed'];

/** Statuses a job may bind to — mirrors PrintRequest.BINDABLE_STATUSES. */
export const LINKABLE_REQUEST_STATUSES = ['approved', 'printing', 'failed', 'completed'];

/** RuneBadge tone per request status. */
export const REQUEST_TONE = {
  pending: 'gold',
  approved: 'moss',
  printing: 'teal',
  completed: 'moss',
  failed: 'ember',
  rejected: 'ember',
  cancelled: 'ink',
};

/** RuneBadge tone per observed job state. */
export const JOB_STATE_TONE = {
  running: 'teal',
  paused: 'gold',
  finished: 'moss',
  failed: 'ember',
  cancelled: 'ink',
  unknown: 'ink',
};

/**
 * Timeline tone per PrintJobEvent.kind. The printer's own alerts (`hms`)
 * and failures read ember; budget debits read gold; everything routine
 * stays ink so the exceptional rows are the ones that catch the eye.
 */
export const EVENT_TONE = {
  started: 'teal',
  progress: 'ink',
  paused: 'gold',
  resumed: 'teal',
  hms: 'ember',
  finished: 'moss',
  failed: 'ember',
  linked: 'royal',
  unlinked: 'ink',
  budget: 'gold',
  note: 'ink',
};

/** HMS severity → tone. Unknown severities fall back to the event's own tone. */
export const SEVERITY_TONE = {
  fatal: 'ember',
  serious: 'ember',
  common: 'gold',
  info: 'ink',
};

/** A job is still streaming while it has no finish time and isn't terminal. */
export function isJobOpen(job) {
  if (!job) return false;
  if (job.finished_at) return false;
  return job.state === 'running' || job.state === 'paused';
}

/** "120 g" — em dash when the value is absent (never "null g"). */
export function formatGrams(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return `${Math.round(n * 100) / 100} g`;
}

/** "3h 20m" / "45m" — minutes only below the hour so short prints read cleanly. */
export function formatMinutes(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Math.round(Number(value));
  if (Number.isNaN(n)) return '—';
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return h > 0 ? `${sign}${h}h ${m}m` : `${sign}${m}m`;
}

/**
 * A null cap means "no cap on that dimension" — see PrintBudget's docstring.
 * Zero is a real value ("nothing this month"), so only null/undefined get
 * the "No cap" treatment.
 */
export function formatCap(value, unit) {
  if (value === null || value === undefined || value === '') return 'No cap';
  return unit === 'minutes' ? formatMinutes(value) : formatGrams(value);
}

/**
 * Remaining can go negative — a parent may approve past the cap with
 * `force`, and a print can overshoot its estimate. We surface the overage
 * rather than clamping, so the tone flips to ember when it does.
 */
export function isOverage(remaining) {
  return remaining !== null && remaining !== undefined && Number(remaining) < 0;
}

/** Percent of a cap consumed, clamped to 0-100. Returns 0 when uncapped. */
export function usagePercent(used, cap) {
  const c = Number(cap);
  if (cap === null || cap === undefined || cap === '' || Number.isNaN(c) || c <= 0) return 0;
  const u = Number(used) || 0;
  return Math.max(0, Math.min(100, (u / c) * 100));
}

/**
 * Verso progress for the folio: how much of this month's filament allowance
 * the household (or the child) has burned. Falls back to a label rather
 * than a bar when nobody has a cap set.
 */
export function budgetProgress(budgets) {
  const capped = budgets.filter(
    (b) => b.grams_per_month !== null && b.grams_per_month !== undefined,
  );
  const usedAll = budgets.reduce((sum, b) => sum + (Number(b.grams_used) || 0), 0);
  if (capped.length === 0) {
    return { pct: 0, label: usedAll > 0 ? `${formatGrams(usedAll)} used this month` : 'no filament cap set' };
  }
  const capTotal = capped.reduce((sum, b) => sum + (Number(b.grams_per_month) || 0), 0);
  const usedCapped = capped.reduce((sum, b) => sum + (Number(b.grams_used) || 0), 0);
  return {
    pct: usagePercent(usedCapped, capTotal),
    label: `${formatGrams(usedCapped)} of ${formatGrams(capTotal)} this month`,
  };
}

/** "62% · layer 120 of 300 · ~45m left" — the pieces that actually exist. */
export function jobProgressLabel(job) {
  if (!job) return '';
  const parts = [`${Math.round(Number(job.percent_complete) || 0)}%`];
  if (job.total_layer_num > 0) {
    parts.push(`layer ${job.layer_num || 0} of ${job.total_layer_num}`);
  }
  if (job.remaining_minutes !== null && job.remaining_minutes !== undefined
      && Number(job.remaining_minutes) > 0) {
    parts.push(`~${formatMinutes(job.remaining_minutes)} left`);
  }
  return parts.join(' · ');
}
