import BottomSheet from '../../components/BottomSheet';
import { RARITY_PILL_COLORS, RARITY_TEXT_COLORS } from '../../constants/colors';
import {
  collectionForBadge,
  ladderSiblings,
  unlockHint,
} from './collections.constants';
import { RARITY_HALO } from '../../components/atlas/mastery.constants';

const TIER_NUMERALS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

/**
 * BadgeDetailSheet — illuminated detail pane for a single sigil. Hero
 * glyph in an ornate ring, rarity ribbon, collection chip ("from the
 * reliquary of {name} · §N"), plain-English unlock hint, optional ladder
 * of sibling badges (shared criterion_type, differing criterion_value),
 * XP bonus line, and a "sealed on {date}" or "not yet earned" footer.
 */
export default function BadgeDetailSheet({ entry, onClose, allBadges = [], earnedIds }) {
  const { badge, earned, earnedAt } = entry;
  const rarity = badge.rarity || 'common';
  const collection = collectionForBadge(badge);
  const ladder = ladderSiblings(badge, allBadges);
  const earnedSet = earnedIds instanceof Set ? earnedIds : new Set(earnedIds ?? []);
  const rawHint = unlockHint(badge);
  // Suppress the hint card if unlockHint fell back to the description we
  // already rendered above — don't echo the same text twice.
  const hint = rawHint && rawHint !== badge.description ? rawHint : '';

  return (
    <BottomSheet title={badge.name} onClose={onClose}>
      <div className="space-y-4">
        {/* Hero sigil */}
        <div className="flex flex-col items-center text-center">
          <div
            className={`relative w-24 h-24 rounded-full border-2 border-ink-page-shadow flex items-center justify-center bg-ink-page-rune-glow shadow-[0_0_0_4px_var(--color-ink-page-aged),0_0_0_5px_var(--color-ink-page-shadow)] ${
              earned ? RARITY_HALO[rarity] || RARITY_HALO.common : ''
            }`}
          >
            <span aria-hidden="true" className={`text-5xl leading-none ${earned ? '' : 'grayscale opacity-50'}`}>
              {badge.icon || '🏅'}
            </span>
          </div>

          <div
            className={`mt-3 inline-flex items-center gap-1 rounded-full px-3 py-1 text-micro font-rune uppercase tracking-wider ${
              RARITY_PILL_COLORS[rarity] || RARITY_PILL_COLORS.common
            }`}
          >
            {rarity}
          </div>

          {collection && (
            <div
              data-collection-chip="true"
              className="mt-2 font-script text-caption text-sheikah-teal-deep"
            >
              from the reliquary of {collection.name} · {collection.rubric}
            </div>
          )}

          {badge.description && (
            <p className="mt-3 text-body text-ink-whisper max-w-prose">
              {badge.description}
            </p>
          )}
        </div>

        {hint && (
          <div
            data-unlock-hint="true"
            className="rounded-xl border border-ink-page-shadow/60 bg-ink-page-aged/60 px-3 py-2 text-center"
          >
            <div className="font-rune uppercase tracking-wider text-micro text-ink-whisper">
              {earned ? 'you earned this by' : 'to earn'}
            </div>
            <div className="mt-0.5 font-script text-body text-ink-primary leading-snug">
              {hint}
            </div>
          </div>
        )}

        {ladder.length >= 2 && (
          <LadderStrip badge={badge} ladder={ladder} earnedIds={earnedSet} />
        )}

        {badge.xp_bonus > 0 && (
          <div className="flex items-center justify-center gap-2 rounded-xl border border-sheikah-teal/30 bg-sheikah-teal/5 px-3 py-2">
            <span className="font-rune text-caption uppercase tracking-wider text-sheikah-teal-deep">
              bonus ink
            </span>
            <span className="font-display text-lede font-bold text-sheikah-teal-deep">
              +{badge.xp_bonus} XP
            </span>
          </div>
        )}

        <div className="text-center">
          {earned ? (
            <div className={`font-script text-lede ${RARITY_TEXT_COLORS[rarity] || 'text-ink-primary'}`}>
              {`sealed ${formatSealDate(earnedAt)}`}
            </div>
          ) : (
            <div className="font-script italic text-ink-whisper">
              not yet earned
            </div>
          )}
        </div>
      </div>
    </BottomSheet>
  );
}

function LadderStrip({ badge, ladder, earnedIds }) {
  const currentIndex = ladder.findIndex((b) => b.id === badge.id);

  return (
    <div data-ladder="true" className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="font-rune uppercase tracking-wider text-micro text-ink-whisper">
          tier ladder
        </span>
        <span className="font-script text-caption text-ink-whisper/80">
          rung {currentIndex + 1} of {ladder.length}
        </span>
      </div>
      <ol className="flex flex-wrap gap-2 list-none p-0 m-0">
        {ladder.map((b, i) => {
          const isCurrent = b.id === badge.id;
          const isEarned = earnedIds.has(b.id);
          return (
            <li key={b.id}>
              <div
                data-ladder-rung={isCurrent ? 'current' : isEarned ? 'earned' : 'locked'}
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 border text-caption font-script ${
                  isCurrent
                    ? 'border-sheikah-teal/60 bg-sheikah-teal/10 text-sheikah-teal-deep'
                    : isEarned
                    ? 'border-moss/50 bg-moss/10 text-moss'
                    : 'border-dashed border-ink-whisper/30 bg-ink-page-aged/40 text-ink-whisper/70'
                }`}
              >
                <span className="font-rune uppercase text-micro tracking-wider">
                  {TIER_NUMERALS[i] ?? i + 1}
                </span>
                <span className="tabular-nums">{b.criterion_value}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function formatSealDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return '';
  }
}
