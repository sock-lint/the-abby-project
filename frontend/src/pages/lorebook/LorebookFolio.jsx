import { useId } from 'react';
import { motion } from 'framer-motion';
import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../achievements/IlluminatedVersal';
import { tierForProgress } from '../achievements/mastery.constants';
import LorebookTile from './LorebookTile';

export default function LorebookFolio({
  chapter,
  entries = [],
  unlocked = 0,
  trained = 0,
  total = 0,
  onSelect,
}) {
  const headingId = useId();
  // Progress band represents inked-page progress (the new training goal),
  // while a quieter whisper line still reports discovery so the auto-element
  // is visible.
  const progressPct = total ? (trained / total) * 100 : 0;
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
        <div className="shrink-0 text-right font-script text-caption text-ink-whisper pt-1 leading-snug">
          <div>
            <span className="tabular-nums">{trained} of {total}</span> inked
          </div>
          <div className="text-micro text-ink-whisper/70">
            <span className="tabular-nums">{unlocked} of {total}</span> discovered
          </div>
        </div>
      </header>

      <div
        aria-hidden="true"
        className="mt-3 h-px bg-gradient-to-r from-transparent via-ink-page-shadow/70 to-transparent"
      />

      <ul className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 md:gap-4 list-none p-0 m-0">
        {entries.map((entry, i) => (
          <motion.li
            key={entry.slug}
            initial={{ scale: 0.92, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{
              delay: Math.min(i, 8) * 0.03,
              duration: 0.28,
              ease: [0.4, 0, 0.2, 1],
            }}
          >
            <LorebookTile entry={entry} onSelect={onSelect} />
          </motion.li>
        ))}
      </ul>
    </ParchmentCard>
  );
}
