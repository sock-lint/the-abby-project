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
 */
export default function IncipitBand({
  letter,
  title,
  kicker,
  meta,
  progressPct = 0,
  rarityCounts,
  versalSize = 'xl',
  className = '',
}) {
  const safePct = Math.max(0, Math.min(100, progressPct));
  const tier = tierForProgress({ unlocked: safePct > 0, progressPct: safePct, level: 0 });

  return (
    <ParchmentCard
      variant="sealed"
      tone="bright"
      flourish
      seal="top-right"
      className={`overflow-hidden ${className}`}
    >
      <div className="flex items-center gap-5 pr-12">
        <IlluminatedVersal
          letter={letter}
          size={versalSize}
          tier={tier}
          progressPct={safePct}
        />
        <div className="flex-1 min-w-0">
          {kicker && (
            <div className="font-script text-sheikah-teal-deep text-base leading-snug">
              {kicker}
            </div>
          )}
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            {title}
          </h1>
          {meta && (
            <div className="mt-1 inline-flex items-center gap-2 text-caption font-script text-ink-whisper">
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
