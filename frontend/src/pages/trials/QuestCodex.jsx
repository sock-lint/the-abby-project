import { useMemo, useState } from 'react';
import TomeShelf from '../../components/atlas/TomeShelf';
import { PROGRESS_TIER } from '../../components/atlas/mastery.constants';
import TrialsFolio from './TrialsFolio';
import {
  CHAPTERS,
  KIND_FILTERS,
  groupQuestsByChapter,
  kindCounts,
} from './trials.constants';

const STORAGE_KEY = 'trials:codex:active-chapter';

/**
 * QuestCodex — kind filters + status collection tabs + active-chapter
 * content. Status buckets show counts, not quest completion progress.
 *
 *   - Kind filters: All / Boss / Collection / Co-op with
 *     `×N` chips. Empty buckets hidden except All.
 *   - Status tabs: 1 Available · 2 Underway · 3 Closed · 4 Locked.
 *     All four tabs render even when empty so the destinations stay clear.
 *   - Folio body: TrialsFolio for the active chapter.
 *
 * localStorage key `trials:codex:active-chapter` persists the chapter
 * across reloads.
 */
export default function QuestCodex({
  available,
  activeQuest,
  history,
  earnedBadgeIds,
  starting,
  onBegin,
  onSelect,
}) {
  const [override, setOverride] = useState(() => {
    try {
      return window.localStorage?.getItem(STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });
  const [kindFilter, setKindFilter] = useState('all');

  const grouped = useMemo(
    () => groupQuestsByChapter({
      available,
      activeQuest,
      history,
      earnedBadgeIds,
    }),
    [available, activeQuest, history, earnedBadgeIds],
  );

  const activeChapterId = useMemo(() => {
    if (override && grouped.some((c) => c.chapter.id === override)) return override;
    // Underway first if a quest is running.
    const underway = grouped.find((c) => c.chapter.id === 'underway' && c.count > 0);
    if (underway) return underway.chapter.id;
    // Otherwise the first non-empty chapter that isn't locked.
    const nonEmpty = grouped.find((c) => c.count > 0 && c.chapter.id !== 'locked');
    if (nonEmpty) return nonEmpty.chapter.id;
    return CHAPTERS[0].id;
  }, [override, grouped]);

  const setActiveChapterId = (id) => {
    setOverride(id);
    try {
      window.localStorage?.setItem(STORAGE_KEY, id);
    } catch { /* ignore quota / disabled storage */ }
  };

  const activeBucket = grouped.find((c) => c.chapter.id === activeChapterId)
    ?? grouped[0];

  // Apply the kind filter to whatever the active chapter holds.
  const filtered = useMemo(() => {
    const filter = KIND_FILTERS.find((f) => f.key === kindFilter) ?? KIND_FILTERS[0];
    return (activeBucket?.quests ?? []).filter(filter.match);
  }, [activeBucket, kindFilter]);

  // Kind counts derive from the active chapter so a filter chip reads
  // "boss ×N in this chapter," matching how Companions/Mounts count.
  const kCounts = useMemo(
    () => kindCounts(activeBucket?.quests ?? []),
    [activeBucket],
  );

  const chapterShelf = grouped.map(({ chapter, count }) => ({
    id: chapter.id,
    name: chapter.name,
    icon: chapter.letter,
    chip: `${count}`,
    // A status bucket has no completion target; progress belongs to each quest.
    progressPct: null,
    tier: count > 0 ? PROGRESS_TIER.nascent : PROGRESS_TIER.locked,
    ariaLabel: `${chapter.name}, ${count} ${count === 1 ? 'challenge' : 'challenges'}`,
  }));

  const visibleKindFilters = KIND_FILTERS.filter(
    ({ key }) => key === 'all' || kCounts[key] > 0,
  );

  const showKindShelf = (activeBucket?.quests?.length ?? 0) > 0
    && visibleKindFilters.length > 1;

  const emptyMessage = activeBucket?.chapter.id === 'available'
    ? 'No challenges available right now.'
    : activeBucket?.chapter.id === 'underway'
      ? 'No active challenge. Choose one from Available to get started.'
      : activeBucket?.chapter.id === 'closed'
        ? 'No completed or ended challenges yet.'
        : 'No locked challenges.';

  // When the filter narrows the chapter to zero rows, distinguish that
  // from "this chapter is empty" — different shape of guidance.
  const filterEmpty = activeBucket?.quests?.length > 0 && filtered.length === 0;

  return (
    <div className="space-y-4">
      {showKindShelf && (
        <TomeShelf
          ariaLabel="Filter challenges by kind"
          activeId={kindFilter}
          onSelect={setKindFilter}
          items={visibleKindFilters.map(({ key, label, icon }) => ({
            id: key,
            name: label,
            icon,
            chip: `×${kCounts[key]}`,
            progressPct: null,
            tier: PROGRESS_TIER.nascent,
            variant: 'vessel',
            ariaLabel: `${label} (${kCounts[key]})`,
          }))}
        />
      )}

      <TomeShelf
        items={chapterShelf}
        activeId={activeChapterId}
        onSelect={setActiveChapterId}
        ariaLabel="Challenge status"
      />

      {activeBucket && (
        <TrialsFolio
          chapter={activeBucket.chapter}
          quests={filterEmpty ? [] : filtered}
          emptyMessage={filterEmpty
            ? `no ${kindFilter} challenges in ${activeBucket.chapter.name.toLowerCase()} — clear the filter to see the rest`
            : emptyMessage}
          hasActiveQuest={!!activeQuest}
          onBegin={onBegin}
          onSelect={onSelect}
          starting={starting}
        />
      )}
    </div>
  );
}
