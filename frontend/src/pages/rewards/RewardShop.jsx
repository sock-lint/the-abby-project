import { Coins, Gift, Pencil, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import { RARITY_COLORS } from '../../constants/colors';

function RewardCard({ reward, isParent, coinBalance, onRedeem, onEdit, onDelete }) {
  const affordable = coinBalance >= reward.cost_coins;
  const outOfStock = reward.stock != null && reward.stock <= 0;

  return (
    <Card className={`${RARITY_COLORS[reward.rarity]} flex flex-col relative`}>
      {isParent && (
        <div className="absolute top-2 right-2 flex gap-1">
          <button
            onClick={() => onEdit(reward)}
            className="p-1 bg-forge-bg/80 hover:bg-forge-muted rounded text-forge-text-dim hover:text-forge-text"
          >
            <Pencil size={12} />
          </button>
          <button
            onClick={() => onDelete(reward.id)}
            className="p-1 bg-forge-bg/80 hover:bg-red-500/30 rounded text-forge-text-dim hover:text-red-300"
          >
            <Trash2 size={12} />
          </button>
        </div>
      )}
      {isParent && !reward.is_active && (
        <div className="text-[10px] text-red-400 text-center mb-1">Inactive</div>
      )}
      <div className="text-3xl mb-1 text-center">{reward.icon || '🎁'}</div>
      <div className="text-sm font-medium text-center">{reward.name}</div>
      {reward.description && (
        <div className="text-xs text-forge-text-dim text-center mt-1 line-clamp-2">
          {reward.description}
        </div>
      )}
      <div className="flex items-center justify-center gap-1 mt-2 text-amber-highlight font-heading font-bold">
        <Coins size={12} /> {reward.cost_coins}
      </div>
      {reward.stock != null && (
        <div className="text-xs text-forge-text-dim text-center">{reward.stock} left</div>
      )}
      {!isParent && (
        <button
          disabled={!affordable || outOfStock}
          onClick={() => onRedeem(reward)}
          className="mt-2 w-full bg-amber-primary hover:bg-amber-highlight disabled:opacity-30 disabled:cursor-not-allowed text-black text-xs font-semibold py-1.5 rounded-lg"
        >
          {outOfStock ? 'Out of stock' : affordable ? 'Redeem' : 'Not enough'}
        </button>
      )}
    </Card>
  );
}

export default function RewardShop({
  rewards, isParent, coinBalance,
  onRedeem, onEdit, onDelete,
}) {
  return (
    <div>
      <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
        <Gift size={18} /> Shop
      </h2>
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
          />
        ))}
      </div>
    </div>
  );
}
