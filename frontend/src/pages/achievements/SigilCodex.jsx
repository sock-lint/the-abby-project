import { useMemo, useState } from 'react';
import EmptyState from '../../components/EmptyState';
import CollectionFolio from './CollectionFolio';
import IncipitBand from '../../components/atlas/IncipitBand';
import TomeShelf from '../../components/atlas/TomeShelf';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import { groupBadgesByCollection, rarityCounts } from './collections.constants';

const STORAGE_KEY = 'atlas:sigil-codex:active-chapter';

/**
 * SigilCodex — top-level layout for the Sigil Case (Atlas → Badges). A
 * hero above seven collection cards grouped by criterion family. Selecting
 * a card opens its CollectionFolio below, preserving earned counts and
 * rarity information while keeping every collection title visible.
 */
export default function SigilCodex({ allBadges = [], earnedBadges = [], onSelect }) {
  const grouped = useMemo(
    () => groupBadgesByCollection(allBadges, earnedBadges),
    [allBadges, earnedBadges],
  );

  // User-clicked override. Persists the kid's choice across re-renders
  // without forcing a setState-in-effect for "data changed" reconciliation:
  // we just derive the effective active id below.
  const [override, setOverride] = useState(() => {
    try {
      return window.localStorage?.getItem(STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });

  // Effective active chapter — derived during render so the active card
  // self-heals when the data shape changes (e.g. a parent edits the badge
  // set and the previously-active chapter no longer exists). Priority:
  // (1) user override that still exists, (2) first chapter with any
  // earned sigil, (3) first chapter overall.
  const activeChapterId = useMemo(() => {
    if (override && grouped.some((c) => c.collection.id === override)) return override;
    const withEarned = grouped.find((c) => c.earned > 0);
    if (withEarned) return withEarned.collection.id;
    return grouped[0]?.collection.id ?? null;
  }, [override, grouped]);

  const setActiveChapterId = (id) => {
    setOverride(id);
    try {
      window.localStorage?.setItem(STORAGE_KEY, id);
    } catch {
      // ignore quota / disabled storage
    }
  };

  if (!allBadges.length) {
    return <EmptyState>No badges available yet.</EmptyState>;
  }

  const earnedIdSet = new Set(earnedBadges.map((ub) => ub?.badge?.id).filter((x) => x != null));
  const totalRarity = rarityCounts(allBadges, earnedIdSet);
  const totalEarned = earnedIdSet.size;
  const total = allBadges.length;
  const progressPct = total ? (totalEarned / total) * 100 : 0;

  const shelfItems = grouped.map((chapter) => {
    const pct = chapter.total ? (chapter.earned / chapter.total) * 100 : 0;
    return {
      id: chapter.collection.id,
      name: chapter.collection.name,
      icon: chapter.collection.letter,
      chip: `${chapter.earned}/${chapter.total}`,
      progressPct: pct,
      tier: tierForProgress({ unlocked: true, progressPct: pct, level: 0 }),
      ariaLabel: `${chapter.collection.name}, ${chapter.earned} of ${chapter.total} earned`,
    };
  });

  const activeChapter = grouped.find((c) => c.collection.id === activeChapterId) ?? grouped[0];

  return (
    <div className="space-y-5">
      <IncipitBand
        letter="B"
        title="Badges"
        kicker="Celebrate what you have achieved"
        meta={
          <>
            <span className="tabular-nums">{totalEarned} of {total}</span>
            <span>earned</span>
          </>
        }
        progressPct={progressPct}
        rarityCounts={totalRarity}
      />

      <TomeShelf
        items={shelfItems}
        activeId={activeChapterId}
        onSelect={setActiveChapterId}
        ariaLabel="Badge collections"
      />

      {activeChapter && (
        <CollectionFolio
          collection={activeChapter.collection}
          badges={activeChapter.badges}
          earned={activeChapter.earned}
          total={activeChapter.total}
          rarityCounts={activeChapter.rarityCounts}
          onSelect={onSelect}
        />
      )}
    </div>
  );
}
