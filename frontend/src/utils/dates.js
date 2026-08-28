export function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDays(date, days) {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

export function quickDueDates(now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dow = today.getDay();

  // Friday = 5. Always land on a future Friday:
  // - From Mon-Thu: this week's Friday.
  // - From Sat or Sun: this week's coming Friday (still future).
  // - From Friday itself: jump to next week's Friday.
  const daysUntilFriday = dow === 5 ? 7 : (5 - dow + 7) % 7;

  // Monday = 1. Always the *next* Monday, even if today is Monday.
  const daysUntilNextMonday = ((1 - dow + 7) % 7) || 7;

  return {
    tomorrow: toISODate(addDays(today, 1)),
    friday: toISODate(addDays(today, daysUntilFriday)),
    nextMonday: toISODate(addDays(today, daysUntilNextMonday)),
    nextWeek: toISODate(addDays(today, 7)),
  };
}

/**
 * Stock ledger ranges for the Payments filter. Answering "did Saturday's
 * payout post?" shouldn't cost two native date-picker sessions — these set
 * both ends in one tap, with the manual fields left as the override.
 */
export function quickRanges(now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dow = today.getDay();
  // Week starts Sunday, matching the app's Sunday timecard rollover.
  const weekStart = addDays(today, -dow);
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const end = toISODate(today);

  return {
    thisWeek: { label: 'This week', start: toISODate(weekStart), end },
    thisMonth: { label: 'This month', start: toISODate(monthStart), end },
    last30: { label: 'Last 30 days', start: toISODate(addDays(today, -30)), end },
    all: { label: 'All time', start: '', end: '' },
  };
}
