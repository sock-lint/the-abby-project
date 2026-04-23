import EmptyState from '../../components/EmptyState';
import CollectionFolio from './CollectionFolio';
import IncipitBand from './IncipitBand';
import { groupBadgesByCollection, rarityCounts } from './collections.constants';

/**
 * SigilCodex — top-level layout for the Sigil Case (Atlas → Badges). A
 * single-row incipit hero above seven reliquary chapters, each grouped by
 * criterion family. Replaces the old flat BadgeSigilGrid so badges speak
 * the same illuminated-manuscript language as the Skills atlas.
 */
export default function SigilCodex({ allBadges = [], earnedBadges = [], onSelect }) {
  if (!allBadges.length) {
    return <EmptyState>No badges have been forged yet.</EmptyState>;
  }

  const grouped = groupBadgesByCollection(allBadges, earnedBadges);
  const earnedIdSet = new Set(earnedBadges.map((ub) => ub?.badge?.id).filter((x) => x != null));
  const totalRarity = rarityCounts(allBadges, earnedIdSet);
  const totalEarned = earnedIdSet.size;

  return (
    <div className="space-y-5">
      <IncipitBand earned={totalEarned} total={allBadges.length} rarityCounts={totalRarity} />

      <div className="space-y-4">
        {grouped.map((chapter) => (
          <CollectionFolio
            key={chapter.collection.id}
            collection={chapter.collection}
            badges={chapter.badges}
            earned={chapter.earned}
            total={chapter.total}
            rarityCounts={chapter.rarityCounts}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}
