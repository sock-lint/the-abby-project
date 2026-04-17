import { RARITY_TEXT_COLORS } from '../../constants/colors';
import { RARITY_HALO, isRecentlyEarned } from './mastery.constants';

/**
 * BadgeSigil — a wax-seal-style badge tile. Earned sigils pulse a rarity
 * halo + foil sheen; unearned ones appear as debossed silhouettes so the
 * grid reads "a collection to fill" rather than "a grid of grey squares".
 *
 * Recently-earned badges (≤ RECENT_EARNED_DAYS) play a one-shot gilded
 * glint that fades after ~1.4s and respects prefers-reduced-motion.
 */
export default function BadgeSigil({ badge, earned, earnedAt, onSelect }) {
  const rarity = badge.rarity || 'common';
  const recent = earned && isRecentlyEarned(earnedAt);

  const earnedShell = `${RARITY_HALO[rarity] || RARITY_HALO.common} bg-ink-page-rune-glow/95 border border-ink-page-shadow`;
  const unearnedShell =
    'border-2 border-dashed border-ink-whisper/30 bg-ink-page-aged/30 text-ink-whisper/55';

  const accessibleName = earned
    ? `${badge.name} · ${rarity}`
    : `${badge.name} · ${rarity} · not yet earned`;

  return (
    <button
      type="button"
      onClick={() =>
        onSelect?.({
          badge,
          earned: !!earned,
          earnedAt: earnedAt ?? null,
        })
      }
      aria-label={accessibleName}
      className="w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal rounded-2xl"
    >
      <div
        data-sigil="true"
        data-earned={earned ? 'true' : 'false'}
        data-rarity={rarity}
        className={`relative rounded-2xl p-3 flex flex-col items-center gap-1.5 min-h-[120px] transition-transform active:scale-[0.98] ${
          earned ? earnedShell : unearnedShell
        } ${recent ? 'animate-gilded-glint' : ''}`}
      >
        {/* Wax-seal icon ring — outer parchment, inner tint */}
        <div
          className={`relative w-14 h-14 rounded-full flex items-center justify-center ${
            earned
              ? 'bg-ink-page-aged shadow-[inset_0_1px_0_rgba(255,248,224,0.6),inset_0_-2px_4px_rgba(45,31,21,0.15)]'
              : ''
          }`}
        >
          <span
            aria-hidden="true"
            className={`text-3xl leading-none ${earned ? '' : 'grayscale opacity-60'}`}
          >
            {badge.icon || '🏅'}
          </span>
        </div>
        <div
          className={`text-caption text-center font-medium leading-tight line-clamp-2 ${
            earned ? 'text-ink-primary' : 'text-ink-whisper/70'
          }`}
        >
          {badge.name}
        </div>
        <div
          className={`text-micro font-rune uppercase tracking-wider ${
            earned ? (RARITY_TEXT_COLORS[rarity] || 'text-ink-secondary') : 'text-ink-whisper/55'
          }`}
        >
          {rarity}
        </div>
      </div>
    </button>
  );
}
