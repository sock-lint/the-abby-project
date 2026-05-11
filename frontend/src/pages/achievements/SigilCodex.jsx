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
 * single-row incipit hero above a TomeShelf of seven reliquary chapters,
 * each grouped by criterion family. Picking a spine opens that chapter's
 * CollectionFolio below; the shelf+single-folio shape matches the Skills
 * page so badges and skills speak the same books-on-a-shelf vocabulary.
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

  // Effective active chapter — derived during render so the active spine
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
    return <EmptyState>No badges have been forged yet.</EmptyState>;
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
      ariaLabel: `${chapter.collection.name}, ${chapter.earned} of ${chapter.total} sealed`,
    };
  });

  const activeChapter = grouped.find((c) => c.collection.id === activeChapterId) ?? grouped[0];

  return (
    <div className="space-y-5">
      <IncipitBand
        letter="S"
        title="Sigil Case"
        kicker="· the reliquary of seals ·"
        meta={
          <>
            <span className="tabular-nums">{totalEarned} of {total}</span>
            <span>sealed</span>
          </>
        }
        progressPct={progressPct}
        rarityCounts={totalRarity}
      />

      <TomeShelf
        items={shelfItems}
        activeId={activeChapterId}
        onSelect={setActiveChapterId}
        ariaLabel="Sigil reliquary chapters"
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
