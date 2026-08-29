import { Pencil, Trash2, Bell, BellRing } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import IconButton from '../../components/IconButton';
import { CoinIcon } from '../../components/icons/JournalIcons';
import { RARITY_COLORS } from '../../constants/colors';

export default function RewardCard({
  reward, isParent, coinBalance, pending, onRedeem, onEdit, onDelete, onToggleWishlist,
}) {
  // coinBalance === null means the balance fetch failed. Greying every
  // Barter button out with "Not enough coin" would be a lie, so an unknown
  // balance lets the tap through and the server rules on it.
  const balanceUnknown = coinBalance === null || coinBalance === undefined;
  const affordable = balanceUnknown || coinBalance >= reward.cost_coins;
  const outOfStock = reward.stock != null && reward.stock <= 0;
  const wishlisted = !!reward.on_my_wishlist;

  return (
    <ParchmentCard
      className={`${RARITY_COLORS[reward.rarity]} flex flex-col relative`}
    >
      {/* Thumb-sized edit/delete, matching the Duties/Rituals card pattern —
          these used to be ~20px marks 4px apart, with destructive Trash2
          immediately beside the safe Pencil in a two-up phone grid. They sit
          in flow rather than floating over the corner so the bigger hit area
          can't land on top of the reward's icon. */}
      {isParent && (
        <div className="flex justify-end gap-2 -mt-2 -mr-1 mb-1">
          <IconButton
            variant="secondary"
            size="sm"
            onClick={() => onEdit(reward)}
            aria-label="Edit reward"
          >
            <Pencil size={14} />
          </IconButton>
          <IconButton
            variant="danger"
            size="sm"
            onClick={() => onDelete(reward.id)}
            aria-label="Delete reward"
          >
            <Trash2 size={14} />
          </IconButton>
        </div>
      )}
      {isParent && !reward.is_active && (
        <div className="font-script text-tiny text-ember-deep text-center mb-1">
          inactive
        </div>
      )}
      <div className="text-4xl mb-1 text-center">{reward.icon || '🎁'}</div>
      <div className="font-body text-body font-semibold text-center text-ink-primary">
        {reward.name}
      </div>
      {reward.description && (
        <div className="font-body text-caption text-ink-secondary text-center mt-1 line-clamp-2">
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
          className={`font-script text-caption text-center ${reward.stock <= 1 ? 'text-ember-deep font-semibold' : 'text-ink-whisper'}`}
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
          {/* Raw markup on purpose: <Button>'s px-3/text-sm sizing wraps
              "Not enough coin" onto three lines inside a ~72px two-up phone
              tile. Keeps the primitive's 44px floor and the type token. */}
          <button
            type="button"
            disabled={!affordable || outOfStock || pending}
            onClick={() => onRedeem(reward)}
            className="flex-1 min-w-0 min-h-11 bg-sheikah-teal-deep hover:bg-sheikah-teal disabled:opacity-40 disabled:cursor-not-allowed text-ink-page-rune-glow text-caption font-body font-semibold leading-tight py-1.5 px-1 rounded-lg border border-sheikah-teal-deep/60 transition-colors"
          >
            {pending ? 'Bartering…' : outOfStock ? 'Out of stock' : affordable ? 'Barter' : 'Not enough coin'}
          </button>
          {onToggleWishlist && (
            <button
              type="button"
              onClick={() => onToggleWishlist(reward)}
              aria-label={wishlisted ? `Remove ${reward.name} from wishlist` : `Add ${reward.name} to wishlist`}
              aria-pressed={wishlisted}
              title={wishlisted ? 'On your wishlist — tap to remove' : 'Notify me when restocked / save for later'}
              className={`shrink-0 min-w-11 flex items-center justify-center rounded-lg border transition-colors ${
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
