import { Gift } from 'lucide-react';
import RewardCard from './RewardCard';

export default function RewardShop({
  rewards, isParent, coinBalance,
  onRedeem, onEdit, onDelete, onToggleWishlist,
}) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <Gift size={18} className="text-sheikah-teal-deep" />
        <div>
          <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
            market stalls
          </div>
          <h2 className="font-display text-xl text-ink-primary leading-tight">Shop</h2>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {rewards.map((r) => (
          <RewardCard
            key={r.id}
            reward={r}
            isParent={isParent}
            coinBalance={coinBalance}
            onRedeem={onRedeem}
            onEdit={onEdit}
            onDelete={onDelete}
            onToggleWishlist={onToggleWishlist}
          />
        ))}
      </div>
    </section>
  );
}
