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
