import BottomSheet from '../../components/BottomSheet';
import EmptyState from '../../components/EmptyState';
import BadgeSigil from '../../components/atlas/BadgeSigil';
import ChapterMarker from '../../components/atlas/ChapterMarker';
import { groupBadgesByCollection } from '../achievements/collections.constants';

/**
 * TrophyBadgePicker — BottomSheet that shows every earned badge grouped
 * by collection. Select a badge to display it as the profile trophy.
 * Select the current trophy to clear the slot.
 *
 * Deliberately reuses `groupBadgesByCollection` + `BadgeSigil` so the
 * picker speaks the exact same visual language as `/atlas?tab=badges`.
 * Earned badges keep the same names, rarity and artwork as the collection.
 */
export default function TrophyBadgePicker({
  allBadges = [],
  earnedBadges = [],
  currentTrophyId,
  onSelect,
  onClose,
}) {
  const badgeMap = new Map(allBadges.map((badge) => [badge.id, badge]));
  for (const { badge } of earnedBadges) if (badge) badgeMap.set(badge.id, { ...badgeMap.get(badge.id), ...badge });
  const completeBadges = [...badgeMap.values()];
  const grouped = groupBadgesByCollection(completeBadges, earnedBadges);
  const grandEarned = earnedBadges.length;

  return (
    <BottomSheet title="Choose your trophy badge" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-center font-script text-ink-whisper text-caption leading-snug">
          Choose an earned badge to show on your profile.
          {currentTrophyId
            ? ' Select your current trophy badge again to remove it.'
            : ''}
        </p>

        {grandEarned === 0 ? (
          <EmptyState>
            You haven’t earned any badges yet. Keep exploring projects and
            challenges to earn your first.
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
                  <div className="flex flex-wrap items-center gap-2">
                    <ChapterMarker>{chapter.collection.rubric}</ChapterMarker>
                    <h3
                      id={`trophy-chapter-${chapter.collection.id}`}
                      className="min-w-0 flex-1 break-words [overflow-wrap:anywhere] font-body font-bold text-body text-ink-primary leading-tight"
                    >
                      {chapter.collection.name}
                    </h3>
                    <span className="font-body text-caption text-ink-secondary">
                      {earnedInChapter.length} earned
                    </span>
                  </div>
                  <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3 list-none p-0 m-0">
                    {earnedInChapter.map((entry) => {
                      const isCurrent = entry.badge.id === currentTrophyId;
                      return (
                        <li key={entry.badge.id} className="min-w-0">
                          <BadgeSigil
                            badge={entry.badge}
                            earned
                            earnedAt={entry.earnedAt}
                            selected={isCurrent}
                            selectionLabel={<span data-trophy-current-marker="true">Current trophy</span>}
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

