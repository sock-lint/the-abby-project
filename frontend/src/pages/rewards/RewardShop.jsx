import { Gift } from 'lucide-react';
import RewardCard from './RewardCard';
import EmptyState from '../../components/EmptyState';
import FilteredEmptyState from '../../components/FilteredEmptyState';

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
          ? 'No rewards yet — head to Manage to add some.'
          : 'No rewards yet — ask a parent to add some.'}
      </EmptyState>
    );
  }

  return (
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
  );
}
