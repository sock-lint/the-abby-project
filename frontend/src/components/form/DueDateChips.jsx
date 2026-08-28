import { quickDueDates } from '../../utils/dates';

/**
 * DueDateChips — one-tap due-date presets for a date field. Native date
 * pickers are slow on phones (a wheel per field), and "tomorrow" or "Friday"
 * covers most of what anyone actually picks.
 *
 * Lifted out of HomeworkFormModal when project creation and editing became
 * the second and third consumers. Fully controlled: the caller owns `value`
 * and applies `onSelect(isoDate)`.
 */
export default function DueDateChips({ value, onSelect, className = '' }) {
  const presets = quickDueDates();
  const rawChips = [
    { label: 'Tomorrow', value: presets.tomorrow, relative: true },
    { label: 'Friday', value: presets.friday, relative: false },
    { label: 'Next Mon', value: presets.nextMonday, relative: false },
    { label: '+1 week', value: presets.nextWeek, relative: true },
  ];
  // Drop a weekday chip that lands on the same day as a relative one, so the
  // row never shows two chips meaning the same date.
  const chips = rawChips.filter((c, i, arr) =>
    c.relative || !arr.some((o, j) => j !== i && o.relative && o.value === c.value),
  );

  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {chips.map((chip) => {
        const active = value === chip.value;
        return (
          <button
            key={chip.label}
            type="button"
            aria-pressed={active}
            onClick={() => onSelect(chip.value)}
            className={
              'min-h-9 px-3 py-1 text-caption font-medium rounded-full border transition-colors '
              + (active
                ? 'bg-sheikah-teal-deep text-ink-page-rune-glow border-sheikah-teal-deep'
                : 'bg-ink-page-aged text-ink-secondary border-ink-page-shadow hover:text-ink-primary')
            }
          >
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}
