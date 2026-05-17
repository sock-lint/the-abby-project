import { useId } from 'react';
import { motion } from 'framer-motion';
import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import { staggerChildren, staggerItem } from '../../motion/variants';
import QuestTile from './QuestTile';

/**
 * TrialsFolio — one status chapter of the Trials codex rendered as a
 * manuscript folio. Rubric numeral + illuminated drop-cap + chapter name
 * above a hair-rule, then the chapter's quests in a 2/3/4-col grid.
 * Mirrors bestiary/codex/BestiaryFolio.jsx so the codex skeleton stays
 * consistent across hubs.
 */
export default function TrialsFolio({
  chapter,
  quests = [],
  emptyMessage = 'no trials filed in this chapter yet',
  hasActiveQuest = false,
  onBegin,
  onSelect,
  starting = null,
}) {
  const headingId = useId();
  // Folio progress reads as "what fraction of this chapter's quests are
  // already in your hands" — we use it to gilt the drop-cap. For status
  // chapters (Available / Closed / Locked) the right denominator is the
  // chapter's own count; for Underway it's effectively binary.
  const progressPct = chapter.id === 'underway' ? (quests.length ? 100 : 0) : 0;
  const tier = tierForProgress({ unlocked: quests.length > 0, progressPct, level: 0 });

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
          <span className="tabular-nums">{quests.length}</span>{' '}
          {quests.length === 1 ? 'trial' : 'trials'}
        </div>
      </header>

      <div
        aria-hidden="true"
        className="mt-3 h-px bg-gradient-to-r from-transparent via-ink-page-shadow/70 to-transparent"
      />

      {quests.length === 0 ? (
        <p className="mt-4 font-script italic text-caption text-ink-whisper/80">
          {emptyMessage}
        </p>
      ) : (
        <motion.div
          variants={staggerChildren}
          initial="initial"
          animate="animate"
          className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-3 lg:grid-cols-4 gap-3"
        >
          {quests.map((q) => (
            <motion.div key={q.id} variants={staggerItem}>
              <QuestTile
                quest={q}
                chapter={chapter.id}
                canBegin={chapter.id === 'available' && !hasActiveQuest}
                starting={starting === q.id}
                onBegin={onBegin}
                onSelect={onSelect}
              />
            </motion.div>
          ))}
        </motion.div>
      )}
    </ParchmentCard>
  );
}
