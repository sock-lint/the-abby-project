import { useMemo, useState } from 'react';
import TomeShelf from '../../components/atlas/TomeShelf';
import { tierForProgress, PROGRESS_TIER } from '../../components/atlas/mastery.constants';
import TrialsFolio from './TrialsFolio';
import {
  CHAPTERS,
  KIND_FILTERS,
  groupQuestsByChapter,
  kindCounts,
} from './trials.constants';

const STORAGE_KEY = 'trials:codex:active-chapter';

/**
 * QuestCodex — vessel filter shelf + codex chapter shelf + active-chapter
 * folio. Mirrors BestiaryCodex's shape so the two hubs speak the same
 * vocabulary.
 *
 *   - Vessel shelf: kind filter (All / Boss / Collection / Co-op) with
 *     `×N` chips. Empty buckets hidden except All.
 *   - Codex shelf: status chapters (§I Available · §II Underway ·
 *     §III Closed · §IV Locked). All four spines render even when empty
 *     so the manuscript skeleton stays intact (matches Bestiary).
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

  // Kind counts derive from the active chapter so a vessel chip reads
  // "boss ×N in this chapter," matching how Companions/Mounts count.
  const kCounts = useMemo(
    () => kindCounts(activeBucket?.quests ?? []),
    [activeBucket],
  );

  const chapterShelf = grouped.map(({ chapter, count }) => {
    const pct = chapter.id === 'underway' ? (count ? 100 : 0)
      : chapter.id === 'closed' ? (count ? Math.min(100, count * 10) : 0)
      : null;
    const tier = tierForProgress({
      unlocked: count > 0,
      progressPct: pct ?? 0,
      level: 0,
    });
    return {
      id: chapter.id,
      name: chapter.name,
      icon: chapter.letter,
      chip: `${count}`,
      progressPct: pct,
      tier,
      ariaLabel: `${chapter.name}, ${count} ${count === 1 ? 'trial' : 'trials'}`,
    };
  });

  const visibleKindFilters = KIND_FILTERS.filter(
    ({ key }) => key === 'all' || kCounts[key] > 0,
  );

  const showKindShelf = (activeBucket?.quests?.length ?? 0) > 0
    && visibleKindFilters.length > 1;

  const emptyMessage = activeBucket?.chapter.id === 'available'
    ? 'no trials posted on the board right now'
    : activeBucket?.chapter.id === 'underway'
      ? 'no trial under way — choose one from Available to begin'
      : activeBucket?.chapter.id === 'closed'
        ? 'no trials in the chronicle yet'
        : 'no badge-gated trials waiting on a seal';

  // When the filter narrows the chapter to zero rows, distinguish that
  // from "this chapter is empty" — different shape of guidance.
  const filterEmpty = activeBucket?.quests?.length > 0 && filtered.length === 0;

  return (
    <div className="space-y-4">
      {showKindShelf && (
        <TomeShelf
          ariaLabel="Filter trials by kind"
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
        ariaLabel="Trials chapters"
      />

      {activeBucket && (
        <TrialsFolio
          chapter={activeBucket.chapter}
          quests={filterEmpty ? [] : filtered}
          emptyMessage={filterEmpty
            ? `no ${kindFilter} trials in ${activeBucket.chapter.name.toLowerCase()} — clear the filter to see the rest`
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
