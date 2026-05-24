import { Gift } from 'lucide-react';
import RewardCard from './RewardCard';
import EmptyState from '../../components/EmptyState';

export default function RewardShop({
  rewards, isParent, coinBalance, pendingId,
  onRedeem, onEdit, onDelete, onToggleWishlist,
}) {
  if (rewards.length === 0) {
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
