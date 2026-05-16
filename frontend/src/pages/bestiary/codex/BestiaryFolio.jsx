import { useId } from 'react';
import { motion } from 'framer-motion';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import IlluminatedVersal from '../../../components/atlas/IlluminatedVersal';
import RarityStrand from '../../../components/atlas/RarityStrand';
import { tierForProgress } from '../../../components/atlas/mastery.constants';
import { staggerChildren, staggerItem } from '../../../motion/variants';
import SpeciesTile from './SpeciesTile';

/**
 * BestiaryFolio — one chapter of the Bestiary Codex. Rubric numeral +
 * illuminated drop-cap + chapter name above a slim rarity strand, then the
 * chapter's species in the existing SpeciesTile grid. Mirrors
 * achievements/CollectionFolio.jsx so the codex skeleton stays consistent
 * across the Atlas and Bestiary hubs.
 */
export default function BestiaryFolio({
  chapter,
  species = [],
  earned = 0,
  total = 0,
  rarityCounts,
  totalPotions,
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
            {chapter.rubric}
          </span>
          <IlluminatedVersal
            letter={chapter.letter}
            size="md"
            tier={tier}
            progressPct={progressPct}
          />
          <div className="min-w-0">
            <h2
              id={headingId}
              className="font-display italic text-xl md:text-2xl text-ink-primary leading-tight truncate"
            >
              {chapter.name}
            </h2>
            <div className="font-script text-caption text-ink-whisper leading-snug truncate">
              {chapter.kicker}
            </div>
          </div>
        </div>
        <div className="shrink-0 text-right font-script text-caption text-ink-whisper pt-1">
          <span className="tabular-nums">{species.length}</span> {species.length === 1 ? 'species' : 'species'}
        </div>
      </header>

      <div className="mt-3">
        <RarityStrand counts={rarityCounts} compact />
      </div>

      <div
        aria-hidden="true"
        className="mt-3 h-px bg-gradient-to-r from-transparent via-ink-page-shadow/70 to-transparent"
      />

      {species.length === 0 ? (
        <p className="mt-4 font-script italic text-caption text-ink-whisper/80">
          no creatures filed in this chapter yet
        </p>
      ) : (
        <motion.div
          variants={staggerChildren}
          initial="initial"
          animate="animate"
          className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
        >
          {species.map((s) => (
            <motion.div key={s.id} variants={staggerItem}>
              <SpeciesTile
                species={s}
                totalPotions={totalPotions}
                onSelect={onSelect}
              />
            </motion.div>
          ))}
        </motion.div>
      )}
    </ParchmentCard>
  );
}
