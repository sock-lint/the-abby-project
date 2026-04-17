import EmptyState from '../EmptyState';
import { formatCurrency } from '../../utils/format';

/**
 * WeekGlanceBlock — per-kid hours + earnings for the current week.
 * Accepts `weekByKid: [{ kid_id, name, hours, earnings }]`.
 */
export default function WeekGlanceBlock({ weekByKid = [] }) {
  if (!weekByKid || weekByKid.length === 0) {
    return <EmptyState>No activity logged this week.</EmptyState>;
  }
  return (
    <ul className="divide-y divide-ink-page-shadow/60">
      {weekByKid.map((row) => (
        <li key={row.kid_id} className="flex items-center justify-between py-2">
          <div className="font-body text-sm text-ink-primary truncate">
            {row.name}
          </div>
          <div className="flex items-center gap-4">
            <div className="font-rune text-xs text-ink-whisper tabular-nums">
              {row.hours ?? 0}h
            </div>
            <div className="font-rune text-xs text-ember-deep tabular-nums">
              {formatCurrency(row.earnings ?? 0)}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
