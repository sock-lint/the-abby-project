import { RARITY_TEXT_COLORS } from '../../constants/colors';
import { RARITY_HALO, isRecentlyEarned } from './mastery.constants';

/**
 * BadgeSigil — a rounded badge tile. Rarity rings and a small XP label
 * distinguish earned badges; readable unlock hints keep future goals clear.
 *
 * `hint` is caller-supplied so the primitive stays domain-agnostic — the
 * Reliquary Codex passes `unlockHint(badge)` from collections.constants;
 * other surfaces can pass a different string or omit it entirely.
 *
 * Recently-earned badges (≤ RECENT_EARNED_DAYS) play a one-shot gilded
 * glint that fades after ~1.4s and respects prefers-reduced-motion.
 */
export default function BadgeSigil({ badge, earned, earnedAt, hint = '', onSelect }) {
  const rarity = badge.rarity || 'common';
  const recent = earned && isRecentlyEarned(earnedAt);
  const visibleHint = earned ? '' : hint;
  const xp = Number(badge.xp_bonus) || 0;

  const earnedShell = `${RARITY_HALO[rarity] || RARITY_HALO.common} bg-ink-page-rune-glow/95 border border-ink-page-shadow`;
  const unearnedShell =
    'border border-dashed border-ink-page-shadow bg-ink-page/70 text-ink-whisper';

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
      className="w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-3xl"
    >
      <div
        data-sigil="true"
        data-earned={earned ? 'true' : 'false'}
        data-rarity={rarity}
        className={`relative rounded-3xl p-3 flex flex-col items-center gap-2 min-h-[136px] transition-transform active:scale-[0.98] ${
          earned ? earnedShell : unearnedShell
        } ${recent ? 'animate-gilded-glint' : ''}`}
      >
        {/* A soft icon surface; unearned icons keep their quiet silhouette. */}
        <div
          className={`relative w-14 h-14 rounded-2xl flex items-center justify-center ${
            earned
              ? 'bg-ink-page-aged'
              : 'bg-ink-page-shadow/20'
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
          className={`text-body text-center font-bold leading-tight line-clamp-2 ${
            earned ? 'text-ink-primary' : 'text-ink-whisper'
          }`}
        >
          {badge.name}
        </div>

        <div
          className={`text-caption font-body ${
            earned ? (RARITY_TEXT_COLORS[rarity] || 'text-ink-secondary') : 'text-ink-whisper'
          }`}
        >
          {rarity}
        </div>

        {/* The unlock hint is what turns the codex into a goal map, so it
            reads at text-tiny in full ink rather than 10px at 80% whisper —
            the tile has the vertical room (min-h 136px). */}
        {!earned && visibleHint && (
          <div
            data-sigil-hint="true"
            className="mt-0.5 text-caption font-body text-center leading-snug text-ink-whisper line-clamp-2 px-1"
          >
            {visibleHint}
          </div>
        )}

        {earned && xp > 0 && (
          <div
            data-sigil-xp="true"
            className="mt-auto pt-1 text-caption font-body font-bold text-gold-leaf"
          >
            +{xp} XP
          </div>
        )}
      </div>
    </button>
  );
}
