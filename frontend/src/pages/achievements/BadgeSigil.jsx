import { RARITY_TEXT_COLORS } from '../../constants/colors';
import { unlockHint } from './collections.constants';
import { RARITY_HALO, isRecentlyEarned } from './mastery.constants';

/**
 * BadgeSigil — a wax-seal badge tile. Earned sigils carry a rarity halo, a
 * foil sheen (for recently-earned), and a thin gilt ledge showing the XP
 * bonus. Unearned sigils render as debossed silhouettes — a pressed
 * intaglio impression with a script unlock hint underneath, so the codex
 * reads as a goal map rather than a grid of empty squares.
 *
 * Recently-earned badges (≤ RECENT_EARNED_DAYS) play a one-shot gilded
 * glint that fades after ~1.4s and respects prefers-reduced-motion.
 */
export default function BadgeSigil({ badge, earned, earnedAt, onSelect }) {
  const rarity = badge.rarity || 'common';
  const recent = earned && isRecentlyEarned(earnedAt);
  const hint = earned ? '' : unlockHint(badge);
  const xp = Number(badge.xp_bonus) || 0;

  const earnedShell = `${RARITY_HALO[rarity] || RARITY_HALO.common} bg-ink-page-rune-glow/95 border border-ink-page-shadow`;
  const unearnedShell =
    'border border-dashed border-ink-whisper/30 bg-ink-page-aged/40 text-ink-whisper/60 shadow-[inset_0_2px_6px_-2px_rgba(45,31,21,0.25),inset_0_-1px_0_rgba(255,248,224,0.4)]';

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
        className={`relative rounded-2xl p-3 flex flex-col items-center gap-1.5 min-h-[136px] transition-transform active:scale-[0.98] ${
          earned ? earnedShell : unearnedShell
        } ${recent ? 'animate-gilded-glint' : ''}`}
      >
        {/* Wax-seal icon ring — outer parchment for earned; pressed intaglio well for unearned. */}
        <div
          className={`relative w-14 h-14 rounded-full flex items-center justify-center ${
            earned
              ? 'bg-ink-page-aged shadow-[inset_0_1px_0_rgba(255,248,224,0.6),inset_0_-2px_4px_rgba(45,31,21,0.15)]'
              : 'bg-ink-page-shadow/25 shadow-[inset_0_2px_4px_rgba(45,31,21,0.35),inset_0_-1px_0_rgba(255,248,224,0.25)]'
          }`}
        >
          <span
            aria-hidden="true"
            className={`text-3xl leading-none ${
              earned ? '' : 'grayscale opacity-45 [filter:grayscale(1)_contrast(0.9)_opacity(0.55)]'
            }`}
          >
            {badge.icon || '🏅'}
          </span>
        </div>

        <div
          className={`text-caption text-center font-medium leading-tight line-clamp-2 ${
            earned ? 'text-ink-primary' : 'text-ink-whisper/75'
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

        {!earned && hint && (
          <div
            data-sigil-hint="true"
            className="mt-0.5 text-micro italic font-script text-center leading-snug text-ink-whisper/80 line-clamp-2 px-1"
          >
            {hint}
          </div>
        )}

        {earned && xp > 0 && (
          <div
            data-sigil-xp="true"
            className="mt-auto pt-1 text-micro font-rune uppercase tracking-wider text-gold-leaf"
          >
            +{xp} XP
          </div>
        )}
      </div>
    </button>
  );
}
