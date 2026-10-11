import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from './IlluminatedVersal';
import RarityStrand from './RarityStrand';
import { tierForProgress } from './mastery.constants';

/**
 * IncipitBand — hero strip for any folio-style chapter opener. Single-row
 * incipit: illuminated drop-cap (letter prop) whose gilt fill reflects
 * `progressPct`, display-serif title, optional script kicker, optional
 * meta line, and an optional rarity strand beneath.
 *
 * Domain-agnostic: the Reliquary Codex passes "Sigil Case" / "sealed of
 * total" copy, the Yearbook can pass a chapter year + a year-progress
 * percent, etc. Pass `rarityCounts` only when a rarity-tier breakdown
 * applies — omit to suppress the strand.
 *
 * Phone-aware by default: with no explicit `versalSize`, the versal renders
 * as a single responsive glyph — md-sized below the sm breakpoint, xl at sm+ —
 * so a 390px phone doesn't spend ~half its content row on ornament. An
 * explicitly-passed `versalSize` opts out and renders a single fixed-size
 * versal at every width (the glyph stays aria-hidden via the primitive).
 */
export default function IncipitBand({
  letter,
  title,
  kicker,
  meta,
  progressPct = 0,
  rarityCounts,
  versalSize,
  className = '',
}) {
  const safePct = Math.max(0, Math.min(100, progressPct));
  const tier = tierForProgress({ unlocked: safePct > 0, progressPct: safePct, level: 0 });

  return (
    <ParchmentCard
      variant="sealed"
      tone="bright"
      className={`overflow-hidden ${className}`}
    >
      <div className="flex items-center gap-3 sm:gap-5">
        <IlluminatedVersal
          letter={letter}
          size={versalSize ?? 'responsive'}
          tier={tier}
          progressPct={safePct}
        />
        <div className="flex-1 min-w-0">
          {kicker && (
            <div className="font-script text-sheikah-teal-deep text-base leading-snug">
              {kicker}
            </div>
          )}
          <h1 className="font-display font-bold text-2xl sm:text-3xl md:text-4xl text-ink-primary leading-tight break-words">
            {title}
          </h1>
          {meta && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-caption font-script text-ink-whisper">
              {meta}
            </div>
          )}
        </div>
      </div>
      {rarityCounts && (
        <div className="mt-4">
          <RarityStrand counts={rarityCounts} />
        </div>
      )}
    </ParchmentCard>
  );
}
