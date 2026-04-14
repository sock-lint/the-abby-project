import RuneBadge from './RuneBadge';

/**
 * PartyCard — active pet (and optionally mount) display.
 *
 * Compact variant is used on the Today page hero strip; full variant is
 * used as the hero of the Party sub-tab.
 *
 * Props:
 *   pet     : { species_name, potion_variant, growth_points, art_url?, rarity? }
 *   mount   : { species_name, art_url? } | null
 *   variant : "compact" | "full"
 *   onFeed  : () => void
 */
export default function PartyCard({
  pet,
  mount,
  variant = 'compact',
  onFeed,
  className = '',
}) {
  if (!pet) {
    return (
      <div
        className={`rounded-xl border border-dashed border-ink-page-shadow bg-ink-page/60 p-4 text-center ${className}`}
      >
        <div className="text-3xl mb-1">🥚</div>
        <div className="font-script text-ink-secondary text-sm">No party member yet</div>
        <div className="font-body text-xs text-ink-whisper mt-0.5">
          Find an egg + potion to hatch
        </div>
      </div>
    );
  }

  const growth = Math.min(100, Math.max(0, pet.growth_points || 0));
  const growthPct = `${growth}%`;

  const compact = variant === 'compact';

  return (
    <div
      className={`relative rounded-xl border border-ink-page-shadow bg-ink-page-rune-glow/60 p-3 ${className}`}
    >
      <div className="flex items-center gap-3">
        {/* Portrait */}
        <div
          className={`${
            compact ? 'w-14 h-14' : 'w-24 h-24'
          } rounded-xl bg-ink-page-aged flex items-center justify-center flex-shrink-0 overflow-hidden shadow-inner`}
        >
          {pet.art_url ? (
            <img src={pet.art_url} alt={pet.species_name} className="w-full h-full object-cover" />
          ) : (
            <span className={compact ? 'text-3xl' : 'text-5xl'}>🐉</span>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-display font-semibold truncate ${compact ? 'text-base' : 'text-xl'}`}>
              {pet.species_name || 'Companion'}
            </span>
            {pet.potion_variant ? (
              <RuneBadge tone="royal" size="sm">
                {pet.potion_variant}
              </RuneBadge>
            ) : null}
          </div>
          {mount && !compact ? (
            <div className="font-script text-xs text-ink-whisper mt-0.5">
              riding: {mount.species_name}
            </div>
          ) : null}

          {/* Growth bar */}
          <div className="mt-2">
            <div className="flex justify-between items-center text-[10px] font-rune text-ink-whisper mb-0.5">
              <span>GROWTH</span>
              <span>{growth}/100</span>
            </div>
            <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-sheikah-teal-deep via-sheikah-teal to-gold-leaf rounded-full transition-[width] duration-500"
                style={{ width: growthPct }}
              />
            </div>
          </div>
        </div>

        {!compact && onFeed ? (
          <button
            type="button"
            onClick={onFeed}
            className="flex-shrink-0 px-3 py-2 rounded-lg bg-moss text-ink-page-rune-glow text-sm font-medium hover:bg-moss/90 transition-colors"
          >
            Feed
          </button>
        ) : null}
      </div>
    </div>
  );
}
