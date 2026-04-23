import { useId, useMemo } from 'react';
import { motion } from 'framer-motion';
import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../achievements/IlluminatedVersal';
import RarityStrand from '../achievements/RarityStrand';
import { tierForProgress } from '../achievements/mastery.constants';
import CosmeticSigil from './CosmeticSigil';
import { mergeSlotCosmetics, slotRarityCounts } from './character.constants';

/**
 * CosmeticChapter — one cosmetic folio in the Frontispiece. Mirrors the
 * Reliquary Codex's `CollectionFolio`: rubric numeral + IlluminatedVersal
 * + script kicker + rarity strand + sigil grid. Owned cosmetics render
 * in full color (with halo + "equipped" ribbon when active); un-owned
 * cosmetics render as debossed intaglios with an unlock hint.
 */
export default function CosmeticChapter({
  chapter,
  owned,
  catalog,
  activeId,
  currentThemeName,
  onEquip,
  onUnequip,
  busy = null,
}) {
  const headingId = useId();
  const entries = useMemo(
    () => mergeSlotCosmetics(chapter.slot, owned, catalog, activeId),
    [chapter.slot, owned, catalog, activeId],
  );
  const ownedCount = entries.filter((e) => e.owned).length;
  const totalCount = entries.length;
  const progressPct = totalCount ? (ownedCount / totalCount) * 100 : 0;
  const tier = tierForProgress({
    unlocked: totalCount > 0,
    progressPct,
    level: 0,
  });
  const rarityCounts = slotRarityCounts(entries);

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
          <span className="tabular-nums">{ownedCount} of {totalCount}</span> owned
        </div>
      </header>

      <div className="mt-3">
        <RarityStrand counts={rarityCounts} compact />
      </div>

      <div
        aria-hidden="true"
        className="mt-3 h-px bg-gradient-to-r from-transparent via-ink-page-shadow/70 to-transparent"
      />

      {entries.length === 0 ? (
        <p className="mt-4 font-script italic text-caption text-ink-whisper/80">
          no cosmetics authored yet
        </p>
      ) : (
        <ul className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 md:gap-4 list-none p-0 m-0">
          {entries.map((entry, i) => (
            <motion.li
              key={entry.item.id}
              initial={{ scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{
                delay: Math.min(i, 8) * 0.03,
                duration: 0.28,
                ease: [0.4, 0, 0.2, 1],
              }}
            >
              <CosmeticSigil
                entry={entry}
                slot={chapter.slot}
                currentThemeName={currentThemeName}
                busy={busy === entry.item.id || busy === chapter.slot}
                onEquip={onEquip}
                onUnequip={onUnequip}
              />
            </motion.li>
          ))}
        </ul>
      )}
    </ParchmentCard>
  );
}
