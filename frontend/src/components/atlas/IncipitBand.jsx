import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from './IlluminatedVersal';
import RarityStrand from './RarityStrand';
import { tierForProgress } from './mastery.constants';

/**
 * IncipitBand — hero strip above the collection folios. A single-row
 * incipit: illuminated drop-cap "S" whose gilt fill reflects overall
 * sealed %, display-serif title, script kicker, a "sealed" count chip,
 * and a full-width rarity strand beneath.
 */
export default function IncipitBand({ earned, total, rarityCounts }) {
  const progressPct = total ? (earned / total) * 100 : 0;
  const tier = tierForProgress({ unlocked: total > 0, progressPct, level: 0 });

  return (
    <ParchmentCard variant="sealed" tone="bright" flourish seal="top-right" className="overflow-hidden">
      <div className="flex items-center gap-5 pr-12">
        <IlluminatedVersal
          letter="S"
          size="xl"
          tier={tier}
          progressPct={progressPct}
        />
        <div className="flex-1 min-w-0">
          <div className="font-script text-sheikah-teal-deep text-base leading-snug">
            · the reliquary of seals ·
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Sigil Case
          </h1>
          <div className="mt-1 inline-flex items-center gap-2 text-caption font-script text-ink-whisper">
            <span className="tabular-nums">
              {earned} of {total}
            </span>
            <span>sealed</span>
          </div>
        </div>
      </div>
      <div className="mt-4">
        <RarityStrand counts={rarityCounts} />
      </div>
    </ParchmentCard>
  );
}
