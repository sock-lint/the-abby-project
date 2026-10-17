import { Gift } from 'lucide-react';
import RewardCard from './RewardCard';
import EmptyState from '../../components/EmptyState';
import FilteredEmptyState from '../../components/FilteredEmptyState';
import ParchmentCard from '../../components/journal/ParchmentCard';
import StorybookFeature from '../../pedestal/StorybookFeature';

export default function RewardShop({
  rewards, isParent, coinBalance, pendingId,
  onRedeem, onEdit, onDelete, onToggleWishlist,
  filterQuery = '', onClearFilter,
}) {
  if (rewards.length === 0) {
    // A search that matches nothing is not the same as an empty bazaar —
    // telling a kid to "ask a parent to add some" while a stocked shop sits
    // behind their own filter sends them off on a false errand.
    const filtering = !!filterQuery.trim() && !!onClearFilter;
    if (filtering) {
      return (
        <FilteredEmptyState
          query={filterQuery.trim()}
          onClear={onClearFilter}
          icon={<Gift size={28} />}
        />
      );
    }
    return (
      <EmptyState icon={<Gift size={28} />}>
        {isParent
          ? 'No rewards yet. Choose New reward to add one.'
          : 'No rewards yet. Ask a parent to add one.'}
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      {!isParent && <ParchmentCard tone="bright">
        <StorybookFeature assetId="card-front-treasure">
          <h3 className="font-body font-bold text-lede text-ink-primary">Choose something to work toward</h3>
          <p className="mt-2 font-body text-body text-ink-secondary">Use your coins to request rewards. Check each reward&apos;s cost and availability below.</p>
        </StorybookFeature>
      </ParchmentCard>}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {rewards.map((r) => (
          <RewardCard
            key={r.id}
            reward={r}
            isParent={isParent}
            coinBalance={coinBalance}
            pending={pendingId === r.id}
            onRedeem={onRedeem}
            onEdit={onEdit}
            onDelete={onDelete}
            onToggleWishlist={onToggleWishlist}
          />
        ))}
      </div>
    </div>
  );
}
