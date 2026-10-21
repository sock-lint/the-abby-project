export const REWARD_UNAVAILABLE_MESSAGE = "A new attempt can't start while this challenge's reward is unavailable.";

export function goalNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 3 }) : '0';
}

export function goalUnit(unit, target) {
  if (unit === 'mi') return Number(target) === 1 ? 'mile' : 'miles';
  if (unit === 'km') return 'km';
  if (unit === 'minutes') return Number(target) === 1 ? 'minute' : 'minutes';
  if (unit === 'damage') return 'damage';
  return Number(target) === 1 ? 'activity' : 'activities';
}

export function goalProgress(goal) {
  return `${goalNumber(goal.progress)} / ${goalNumber(goal.target)} ${goalUnit(goal.unit, goal.target)}`;
}

export function goalTargetSummary(goal) {
  const amount = Number(goal.target);
  const target = Number.isFinite(amount) && amount > 0
    ? `${goalNumber(amount)} ${['count', 'minutes', 'distance', 'damage'].includes(goal.metric) ? goalUnit(goal.unit, amount) : 'target'}`
    : 'Target unavailable';
  return `${target} · ${goal.what_counts || 'Qualifying activity unavailable'}`;
}

export function goalPeriod(goal, timezone = 'UTC') {
  const start = new Date(goal.starts_at);
  const end = new Date(Date.parse(goal.ends_at) - 1);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) return '';
  const format = (date) => {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    try { return new Intl.DateTimeFormat(undefined, { ...options, timeZone: goal.timezone || timezone }).format(date); }
    catch { return new Intl.DateTimeFormat(undefined, { ...options, timeZone: 'UTC' }).format(date); }
  };
  return `Goal period ${format(start)} – ${format(end)}`;
}

// Presentation filtering uses the final included date in the saved zone.
// It does not decide whether work qualifies or whether a goal has expired.
export function goalFinalDate(goal, timezone = 'UTC') {
  const date = new Date(Date.parse(goal.ends_at) - 1);
  if (!Number.isFinite(date.getTime())) return '';
  const format = (timeZone) => Object.fromEntries(new Intl.DateTimeFormat('en', {
    year: 'numeric', month: '2-digit', day: '2-digit', timeZone,
  }).formatToParts(date).map(({ type, value }) => [type, value]));
  let parts;
  try { parts = format(goal.timezone || timezone); } catch { parts = format('UTC'); }
  return `${parts.year}-${parts.month}-${parts.day}`;
}

// End timestamps are exclusive. Show the final included day in the family's zone.
export function goalDate(value, timezone = 'UTC', withYear = false) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', timeZone: timezone, ...(withYear && { year: 'numeric' }),
  }).format(date);
}

export function goalDeadline(endsAt, timezone = 'UTC') {
  if (!endsAt) return '';
  return goalDate(new Date(new Date(endsAt).getTime() - 1), timezone);
}

export function goalActionPath(action) {
  if (!action?.path?.startsWith('/') || action.path.startsWith('//')) return null;
  if (!action.movement_type_id) return action.path;
  const query = new URLSearchParams(action.path.split('?')[1] || '');
  query.set('log', '1');
  query.set('movement_type', String(action.movement_type_id));
  return `${action.path.split('?')[0]}?${query}`;
}
