const DAY_MS = 24 * 60 * 60 * 1000;

function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const date = new Date(`${value}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) return null;
  return date;
}

function appToday(now) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Phoenix', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (type) => parts.find((item) => item.type === type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function isoWeek(date) {
  const thursday = new Date(date);
  thursday.setUTCDate(thursday.getUTCDate() + 4 - (thursday.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  return Math.ceil(((thursday - yearStart) / DAY_MS + 1) / 7);
}

function activeOnDate(chore, date) {
  if (chore.week_schedule !== 'alternating' || !chore.schedule_start_date) return true;
  const reference = parseDate(chore.schedule_start_date);
  // Match ChoreService.is_active_this_week: ISO week parity resets each year,
  // so an uninterrupted 14-day recurrence would be wrong after week 53.
  return reference !== null && isoWeek(date) % 2 === isoWeek(reference) % 2;
}

export function nextChoreReminderDate(chore, today = appToday(new Date())) {
  const first = parseDate(today);
  if (!first) return null;
  // At the boundary of a 53-week ISO year, an off period can span two weeks.
  for (let offset = 0; offset <= 14; offset += 1) {
    const date = new Date(first.getTime() + offset * DAY_MS);
    if (activeOnDate(chore, date)) return date.toISOString().slice(0, 10);
  }
  return null;
}

export function validateChoreReminderDate(chore, value) {
  const date = parseDate(value);
  if (!date) return 'Choose a valid day for this chore reminder.';
  if (!activeOnDate(chore, date)) return 'This chore is off that week. Choose a day in an on-week.';
  return '';
}

export function choreReminderEvent(chore, now = new Date()) {
  if (chore.is_active === false || chore.pending_parent_review) return null;
  const start = nextChoreReminderDate(chore, appToday(now));
  if (!start) return null;
  return {
    id: `chore:${chore.id}`,
    title: `Chore reminder: ${chore.title}`,
    start,
    description: 'A one-day reminder for this chore.',
    path: '/quests?tab=duties',
  };
}
