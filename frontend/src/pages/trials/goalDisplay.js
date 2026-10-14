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

// End timestamps are exclusive. Show the final included day in the family's zone.
export function goalDate(value, timezone = 'UTC') {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', timeZone: timezone,
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
