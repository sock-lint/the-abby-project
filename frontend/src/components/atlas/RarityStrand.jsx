import { RARITY_KEYS } from './mastery.constants';

// Rarity → fill bg + muted trough bg. Same token vocabulary the sigils and
// IlluminatedVersals already use, so covers (hyrule / vigil / sunlit / …) stay
// contrast-tuned without a per-cover branch here.
const TROUGH = {
  common: 'bg-moss/15',
  uncommon: 'bg-sheikah-teal/15',
  rare: 'bg-royal/15',
  epic: 'bg-ember/15',
  legendary: 'bg-gold-leaf/20',
};

const FILL = {
  common: 'bg-moss',
  uncommon: 'bg-sheikah-teal-deep',
  rare: 'bg-royal',
  epic: 'bg-ember',
  legendary: 'bg-gold-leaf',
};

/**
 * RarityStrand — a slim five-segment band that reads like an illumination
 * ribbon across the head of a folio. Each segment is sized by the count of
 * badges at that rarity; the foreground fill inside the segment grows with
 * `earned / total`. Decorative from a semantic standpoint (role="img") with
 * a descriptive aria-label so screen readers get the same summary.
 *
 * Reduced-motion users skip the width transition — the strand still paints,
 * just without the inking animation.
 */
export default function RarityStrand({ counts, compact = false, className = '' }) {
  const safeCounts = counts ?? {};
  const segments = RARITY_KEYS.map((key) => ({
    key,
    earned: safeCounts[key]?.earned ?? 0,
    total: safeCounts[key]?.total ?? 0,
  }));
  const grandTotal = segments.reduce((sum, s) => sum + s.total, 0);
  const grandEarned = segments.reduce((sum, s) => sum + s.earned, 0);

  const label = grandTotal
    ? segments.map((s) => `${s.earned} of ${s.total} ${s.key}`).join(', ')
    : 'no seals catalogued';

  const height = compact ? 'h-1' : 'h-2';

  if (!grandTotal) {
    return (
      <div
        role="img"
        aria-label={label}
        className={`relative w-full ${height} rounded-full bg-ink-page-shadow/40 ${className}`}
      />
    );
  }

  return (
    <div
      role="img"
      aria-label={`${grandEarned} of ${grandTotal} sealed — ${label}`}
      className={`relative w-full ${height} flex overflow-hidden rounded-full bg-ink-page-shadow/25 ${className}`}
    >
      {segments.map((s) => {
        if (!s.total) return null;
        const width = (s.total / grandTotal) * 100;
        const fillPct = s.total ? Math.round((s.earned / s.total) * 100) : 0;
        return (
          <div
            key={s.key}
            data-rarity={s.key}
            className={`relative ${TROUGH[s.key]}`}
            style={{ width: `${width}%` }}
          >
            <div
              className={`absolute inset-y-0 left-0 ${FILL[s.key]} motion-safe:transition-[width] motion-safe:duration-500 motion-safe:ease-out`}
              style={{ width: `${fillPct}%` }}
            />
          </div>
        );
      })}
    </div>
  );
}
