import { useId } from 'react';
import { motion } from 'framer-motion';
import ParchmentCard from '../../components/journal/ParchmentCard';
import BadgeSigil from './BadgeSigil';
import IlluminatedVersal from './IlluminatedVersal';
import RarityStrand from './RarityStrand';
import { tierForProgress } from './mastery.constants';

/**
 * CollectionFolio — one chapter in the reliquary codex. Rubric numeral +
 * illuminated drop-cap + chapter name above a slim rarity strand, then the
 * chapter's sigils in the same 2→5-col grid the page had before. Empty
 * chapters still render their heading so the codex skeleton stays legible
 * for users with only a few badges catalogued.
 */
export default function CollectionFolio({
  collection,
  badges = [],
  earned = 0,
  total = 0,
  rarityCounts,
  onSelect,
}) {
  const headingId = useId();
  const progressPct = total ? (earned / total) * 100 : 0;
  const tier = tierForProgress({ unlocked: total > 0, progressPct, level: 0 });

  return (
    <ParchmentCard as="section" variant="plain" tone="default" aria-labelledby={headingId}>
      <header className="flex items-start gap-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span
            aria-hidden="true"
            className="font-display italic text-2xl text-ink-secondary/70 leading-none tabular-nums pt-1"
          >
            {collection.rubric}
          </span>
          <IlluminatedVersal
            letter={collection.letter}
            size="md"
            tier={tier}
            progressPct={progressPct}
          />
          <div className="min-w-0">
            <h2
              id={headingId}
              className="font-display italic text-xl md:text-2xl text-ink-primary leading-tight truncate"
            >
              {collection.name}
            </h2>
            <div className="font-script text-caption text-ink-whisper leading-snug truncate">
              {collection.kicker}
            </div>
          </div>
        </div>
        <div className="shrink-0 text-right font-script text-caption text-ink-whisper pt-1">
          <span className="tabular-nums">{earned} of {total}</span> sealed
        </div>
      </header>

      <div className="mt-3">
        <RarityStrand counts={rarityCounts} compact />
      </div>

      <div
        aria-hidden="true"
        className="mt-3 h-px bg-gradient-to-r from-transparent via-ink-page-shadow/70 to-transparent"
      />

      {badges.length === 0 ? (
        <p className="mt-4 font-script italic text-caption text-ink-whisper/80">
          no seals yet in this chapter
        </p>
      ) : (
        <ul className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 md:gap-4 list-none p-0 m-0">
          {badges.map((item, i) => (
            <motion.li
              key={item.badge.id}
              initial={{ scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{
                delay: Math.min(i, 8) * 0.03,
                duration: 0.28,
                ease: [0.4, 0, 0.2, 1],
              }}
            >
              <BadgeSigil
                badge={item.badge}
                earned={item.earned}
                earnedAt={item.earnedAt}
                onSelect={onSelect}
              />
            </motion.li>
          ))}
        </ul>
      )}
    </ParchmentCard>
  );
}
