import { Pencil, Trash2, Gift } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { CoinIcon } from '../../components/icons/JournalIcons';
import { RARITY_COLORS } from '../../constants/colors';

function RewardCard({ reward, isParent, coinBalance, onRedeem, onEdit, onDelete }) {
  const affordable = coinBalance >= reward.cost_coins;
  const outOfStock = reward.stock != null && reward.stock <= 0;

  return (
    <ParchmentCard
      className={`${RARITY_COLORS[reward.rarity]} flex flex-col relative`}
    >
      {isParent && (
        <div className="absolute top-2 right-2 flex gap-1">
          <button
            type="button"
            onClick={() => onEdit(reward)}
            aria-label="Edit reward"
            className="p-1 bg-ink-page/80 hover:bg-ink-page-aged rounded text-ink-secondary hover:text-ink-primary transition-colors"
          >
            <Pencil size={12} />
          </button>
          <button
            type="button"
            onClick={() => onDelete(reward.id)}
            aria-label="Delete reward"
            className="p-1 bg-ink-page/80 hover:bg-ember/30 rounded text-ink-secondary hover:text-ember-deep transition-colors"
          >
            <Trash2 size={12} />
          </button>
        </div>
      )}
      {isParent && !reward.is_active && (
        <div className="font-script text-tiny text-ember-deep text-center mb-1">
          inactive
        </div>
      )}
      <div className="text-4xl mb-1 text-center">{reward.icon || '🎁'}</div>
      <div className="font-body text-sm font-semibold text-center text-ink-primary">
        {reward.name}
      </div>
      {reward.description && (
        <div className="font-body text-xs text-ink-secondary text-center mt-1 line-clamp-2">
          {reward.description}
        </div>
      )}
      <div className="flex items-center justify-center gap-1 mt-2 text-gold-leaf font-rune font-bold">
        <CoinIcon size={14} className="text-gold-leaf" />
        {reward.cost_coins}
      </div>
      {reward.stock != null && (
        <div className="font-script text-xs text-ink-whisper text-center">
          {reward.stock} left
        </div>
      )}
      {!isParent && (
        <button
          type="button"
          disabled={!affordable || outOfStock}
          onClick={() => onRedeem(reward)}
          className="mt-2 w-full bg-sheikah-teal-deep hover:bg-sheikah-teal disabled:opacity-40 disabled:cursor-not-allowed text-ink-page-rune-glow text-xs font-body font-semibold py-1.5 rounded-lg border border-sheikah-teal-deep/60 transition-colors"
        >
          {outOfStock ? 'Out of stock' : affordable ? 'Barter' : 'Not enough coin'}
        </button>
      )}
    </ParchmentCard>
  );
}

export default function RewardShop({
  rewards, isParent, coinBalance,
  onRedeem, onEdit, onDelete,
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
          />
        ))}
      </div>
    </section>
  );
}
