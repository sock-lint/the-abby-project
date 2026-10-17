import BadgeRarity from '../atlas/BadgeRarity';
import CatalogIcon from './CatalogIcon';

/** Reward previews and receipts share artwork/rarity, with old receipts allowed
 * to omit details that were not recorded when the reward was granted. */
export default function RewardItem({ item, showQuantity = true }) {
  const name = item.item_name || item.name || 'Item';
  const rarity = item.item_rarity || item.rarity;
  const quantity = item.quantity ?? 1;
  const salvage = item.salvaged_to_coins;
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-xl border border-ink-page-shadow/60 bg-ink-page-aged/60 px-3 py-2">
      <CatalogIcon
        assetId={item.item_catalog_icon || item.catalog_icon}
        spriteKey={item.item_sprite_key || item.sprite_key}
        icon={item.item_icon || item.icon || '🎁'}
        size={32}
        alt=""
      />
      <div className="min-w-0 space-y-1 font-body text-caption text-ink-primary">
        <p className="break-words">{name}{showQuantity || quantity > 1 ? ` ×${quantity}` : ''}</p>
        {rarity && <BadgeRarity rarity={rarity} />}
        {(item.item_effect_summary || item.effect_summary) && <p className="text-ink-secondary">{item.item_effect_summary || item.effect_summary}</p>}
        {salvage !== undefined && salvage !== null && (
          <p className="text-ink-secondary">Duplicate exchanged for {salvage} coins</p>
        )}
      </div>
    </div>
  );
}
