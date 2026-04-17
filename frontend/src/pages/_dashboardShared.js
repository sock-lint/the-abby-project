// Shared helpers lifted out of the old Dashboard.jsx so ChildDashboard and
// ParentDashboard can reuse them without circular imports.

export function formatWeekdayDate(d = new Date()) {
  const weekday = d.toLocaleDateString(undefined, { weekday: 'long' });
  const dateStr = d.toLocaleDateString(undefined, { month: 'long', day: 'numeric' });
  return { weekday, dateStr };
}

export function mapProjectTone(status) {
  switch (status) {
    case 'completed': return 'moss';
    case 'in_review': return 'royal';
    case 'in_progress': return 'ember';
    case 'active': return 'teal';
    case 'archived':
    case 'draft': return 'ink';
    default: return 'teal';
  }
}

export function streakMultiplier(loginStreak) {
  if (!loginStreak) return null;
  return Math.min(1 + loginStreak * 0.07, 2).toFixed(2);
}
