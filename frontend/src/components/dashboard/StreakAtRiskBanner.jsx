import { Flame } from 'lucide-react';
import { toISODate } from '../../utils/dates';

// Streaks shorter than this aren't worth alarming over — mirrors
// STREAK_AT_RISK_MIN in apps/rpg/tasks.py.
const MIN_STREAK = 3;

/**
 * StreakAtRiskBanner — soft warning when today has no logged activity yet
 * and a streak of 3+ days is on the line. Companion to the 19:00
 * streak_at_risk notification; this surfaces the same signal in-page.
 * Not dismissible by design: it disappears on its own the moment the kid
 * logs anything, because the dashboard reload advances last_active_date.
 */
export default function StreakAtRiskBanner({ rpg }) {
  const streak = rpg?.login_streak ?? 0;
  const lastActive = rpg?.last_active_date;
  if (streak < MIN_STREAK || !lastActive) return null;
  if (lastActive >= toISODate(new Date())) return null;

  return (
    <div
      role="status"
      className="rounded-lg border border-ember/40 bg-ember/10 px-4 py-2 text-body text-ink-primary flex items-start gap-3"
    >
      <Flame size={16} className="text-ember-deep shrink-0 mt-1" aria-hidden="true" />
      <span className="flex-1 font-script">
        Your {streak}-day streak is waiting — log anything today to keep the
        flame alive.
      </span>
    </div>
  );
}
