import BottomSheet from '../../components/BottomSheet';
import EmptyState from '../../components/EmptyState';
import BadgeSigil from '../achievements/BadgeSigil';
import { groupBadgesByCollection } from '../achievements/collections.constants';

/**
 * TrophyBadgePicker — BottomSheet that shows every earned badge grouped
 * by its Reliquary Codex chapter. Click a sigil to set it as the hero
 * trophy. Click the current trophy to clear the slot.
 *
 * Deliberately reuses `groupBadgesByCollection` + `BadgeSigil` so the
 * picker speaks the exact same visual language as `/atlas?tab=badges`.
 * The child never needs to mentally re-map — the seal that was sitting
 * in their reliquary is the same seal that can stand on their hero plate.
 */
export default function TrophyBadgePicker({
  allBadges = [],
  earnedBadges = [],
  currentTrophyId,
  onSelect,
  onClose,
}) {
  const grouped = groupBadgesByCollection(allBadges, earnedBadges);
  const grandEarned = earnedBadges.length;

  return (
    <BottomSheet title="Choose your hero seal" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-center font-script text-ink-whisper text-caption leading-snug">
          pick the seal you wish to display on your frontispiece.
          {currentTrophyId
            ? ' Click your current seal again to clear the slot.'
            : ''}
        </p>

        {grandEarned === 0 ? (
          <EmptyState>
            You haven’t earned any seals yet — finish a quest or complete a
            project to forge your first.
          </EmptyState>
        ) : (
          <div className="space-y-4">
            {grouped.map((chapter) => {
              const earnedInChapter = chapter.badges.filter((b) => b.earned);
              if (earnedInChapter.length === 0) return null;
              return (
                <section
                  key={chapter.collection.id}
                  aria-labelledby={`trophy-chapter-${chapter.collection.id}`}
                  className="space-y-2"
                >
                  <div className="flex items-baseline gap-2">
                    <span
                      aria-hidden="true"
                      className="font-display italic text-ink-secondary/70 text-caption tabular-nums"
                    >
                      {chapter.collection.rubric}
                    </span>
                    <h3
                      id={`trophy-chapter-${chapter.collection.id}`}
                      className="font-display italic text-body text-ink-primary leading-tight"
                    >
                      {chapter.collection.name}
                    </h3>
                    <span className="font-script text-micro text-ink-whisper ml-auto">
                      {earnedInChapter.length} sealed
                    </span>
                  </div>
                  <ul className="grid grid-cols-3 sm:grid-cols-4 gap-2 list-none p-0 m-0">
                    {earnedInChapter.map((entry) => {
                      const isCurrent = entry.badge.id === currentTrophyId;
                      return (
                        <li key={entry.badge.id} className="relative">
                          {isCurrent && (
                            <div
                              aria-hidden="true"
                              data-trophy-current-marker="true"
                              className="absolute -top-1 left-1/2 -translate-x-1/2 z-10 rounded-full bg-sheikah-teal-deep px-2 py-0.5 text-micro font-rune uppercase tracking-wider text-ink-page-rune-glow shadow-md"
                            >
                              current
                            </div>
                          )}
                          <BadgeSigil
                            badge={entry.badge}
                            earned
                            earnedAt={entry.earnedAt}
                            onSelect={({ badge }) =>
                              onSelect?.(isCurrent ? null : badge.id)
                            }
                          />
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </BottomSheet>
  );
}

