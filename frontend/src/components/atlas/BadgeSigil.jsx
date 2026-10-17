import { RARITY_HALO, isRecentlyEarned } from './mastery.constants';
import BadgeArtwork from './BadgeArtwork';
import BadgeRarity from './BadgeRarity';

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
export default function BadgeSigil({ badge, earned, earnedAt, hint = '', onSelect, selected, selectionLabel = 'Selected' }) {
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
      aria-pressed={selected}
      className="min-w-0 max-w-full w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-3xl"
    >
      <div
        data-sigil="true"
        data-earned={earned ? 'true' : 'false'}
        data-rarity={rarity}
        className={`relative rounded-3xl p-3 flex flex-col items-center gap-2 min-h-[136px] transition-transform active:scale-[0.98] ${
          earned ? earnedShell : unearnedShell
        } ${recent ? 'animate-gilded-glint' : ''}`}
      >
        <BadgeArtwork badge={badge} earned={earned} />

        <div
          className={`min-w-0 max-w-full break-words [overflow-wrap:anywhere] text-body text-center font-bold leading-tight line-clamp-2 ${
            earned ? 'text-ink-primary' : 'text-ink-whisper'
          }`}
        >
          {badge.name}
        </div>

        <BadgeRarity rarity={rarity} quiet={!earned} />

        {/* The unlock hint is what turns the codex into a goal map, so it
            reads at text-tiny in full ink rather than 10px at 80% whisper —
            the tile has the vertical room (min-h 136px). */}
        {!earned && visibleHint && (
          <div
            data-sigil-hint="true"
            className="mt-0.5 min-w-0 max-w-full break-words [overflow-wrap:anywhere] text-caption font-body text-center leading-snug text-ink-whisper line-clamp-2 px-1"
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
        {badge.coin_bonus > 0 && <div className="font-body text-caption font-semibold text-gold-leaf">+{badge.coin_bonus} coins base</div>}
        {selected !== undefined && <span data-sigil-selection={selected ? 'true' : 'false'}
          className="min-h-6 max-w-full break-words [overflow-wrap:anywhere] font-body text-caption font-semibold text-sheikah-teal-deep">
          {selected ? selectionLabel : null}
        </span>}
      </div>
    </button>
  );
}
