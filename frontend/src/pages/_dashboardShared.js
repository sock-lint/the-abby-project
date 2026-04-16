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

/**
 * Next-due target for the dashboard's "upcoming homework" peek.
 *
 * If today is Mon–Thu, targets tomorrow. If Fri/Sat/Sun, targets the next
 * Monday — the school-work cadence is weekday-bound, so weekend homework
 * cues should point to Monday morning.
 *
 * Returns `{ iso, label, weekdayIndex }` where iso is "YYYY-MM-DD" in local
 * time (no timezone math — matches Django's `DueDateField` local-date
 * storage).
 */
export function nextDueTarget(today = new Date()) {
  const dow = today.getDay(); // 0=Sun … 6=Sat
  let delta;
  let label;
  if (dow === 5) { delta = 3; label = 'Monday'; }            // Fri → Mon
  else if (dow === 6) { delta = 2; label = 'Monday'; }       // Sat → Mon
  else if (dow === 0) { delta = 1; label = 'Monday'; }       // Sun → Mon
  else { delta = 1; label = 'tomorrow'; }                    // Mon–Thu
  const target = new Date(today.getFullYear(), today.getMonth(), today.getDate() + delta);
  const iso = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}-${String(target.getDate()).padStart(2, '0')}`;
  return { iso, label, weekdayIndex: target.getDay() };
}
