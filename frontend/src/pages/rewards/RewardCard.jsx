import { Pencil, Trash2, Bell, BellRing } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { CoinIcon } from '../../components/icons/JournalIcons';
import { RARITY_COLORS } from '../../constants/colors';

export default function RewardCard({
  reward, isParent, coinBalance, onRedeem, onEdit, onDelete, onToggleWishlist,
}) {
  const affordable = coinBalance >= reward.cost_coins;
  const outOfStock = reward.stock != null && reward.stock <= 0;
  const wishlisted = !!reward.on_my_wishlist;

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
      {reward.fulfillment_kind && reward.fulfillment_kind !== 'real_world' && (
        <div className="mt-2 rounded-full border border-sheikah-teal/40 bg-sheikah-teal-deep/10 px-2 py-1 text-center font-script text-tiny text-sheikah-teal-deep">
          Adds {reward.item_definition_detail?.name || 'an item'} to Satchel
          {reward.fulfillment_kind === 'both' ? ' + parent follow-up' : ''}
        </div>
      )}
      <div className="flex items-center justify-center gap-1 mt-2 text-gold-leaf font-rune font-bold">
        <CoinIcon size={14} className="text-gold-leaf" />
        {reward.cost_coins}
      </div>
      {reward.stock != null && (
        <div
          className={`font-script text-xs text-center ${reward.stock <= 1 ? 'text-ember-deep font-semibold' : 'text-ink-whisper'}`}
        >
          {reward.stock === 0
            ? 'sold out'
            : reward.stock === 1
              ? 'last one'
              : `${reward.stock} left`}
        </div>
      )}
      {!isParent && (
        <div className="mt-2 flex items-stretch gap-1.5">
          <button
            type="button"
            disabled={!affordable || outOfStock}
            onClick={() => onRedeem(reward)}
            className="flex-1 bg-sheikah-teal-deep hover:bg-sheikah-teal disabled:opacity-40 disabled:cursor-not-allowed text-ink-page-rune-glow text-xs font-body font-semibold py-1.5 rounded-lg border border-sheikah-teal-deep/60 transition-colors"
          >
            {outOfStock ? 'Out of stock' : affordable ? 'Barter' : 'Not enough coin'}
          </button>
          {onToggleWishlist && (
            <button
              type="button"
              onClick={() => onToggleWishlist(reward)}
              aria-label={wishlisted ? `Remove ${reward.name} from wishlist` : `Add ${reward.name} to wishlist`}
              aria-pressed={wishlisted}
              title={wishlisted ? 'On your wishlist — tap to remove' : 'Notify me when restocked / save for later'}
              className={`shrink-0 px-2 rounded-lg border transition-colors ${
                wishlisted
                  ? 'bg-gold-leaf/20 border-gold-leaf/60 text-gold-leaf'
                  : 'bg-ink-page-aged hover:bg-ink-page-shadow/50 border-ink-page-shadow/30 text-ink-whisper hover:text-gold-leaf'
              }`}
            >
              {wishlisted ? <BellRing size={14} /> : <Bell size={14} />}
            </button>
          )}
        </div>
      )}
    </ParchmentCard>
  );
}
