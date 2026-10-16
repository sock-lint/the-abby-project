import Button from '../../components/Button';
import { Link } from 'react-router-dom';
import ParchmentCard from '../../components/journal/ParchmentCard';
import CatalogIcon from '../../components/rpg/CatalogIcon';
import { isCatalogAvailable } from '../../utils/catalogAvailability';
import { itemDisplayName } from '../../utils/itemDisplayName';

export default function SavedCosmetics({ cosmetics, profile, working, onRemove }) {
  const stored = Object.entries(cosmetics || {}).flatMap(([slot, items]) => (Array.isArray(items) ? items : [])
    .filter((item) => slot === 'active_pet_accessory' || !isCatalogAvailable(item))
    .map((item) => ({ item, slot })));
  if (profile.active_pet_accessory && !stored.some(({ item }) => item.id === profile.active_pet_accessory.id)) {
    stored.push({ item: profile.active_pet_accessory, slot: 'active_pet_accessory' });
  }
  if (!stored.length) return null;
  return <ParchmentCard as="section" aria-label="Saved collection" className="space-y-3">
    <div>
      <h2 className="font-body font-bold text-lede text-ink-primary">Saved collection <span className="font-normal text-caption text-ink-secondary">· {stored.length} {stored.length === 1 ? 'item' : 'items'}</span></h2>
      <p className="font-body text-caption text-ink-secondary">Your earlier items stay here as keepsakes. They are not available for customization.</p>
    </div>
    <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3 list-none">
      {stored.map(({ item, slot }) => <li key={item.id} className="rounded-xl border border-ink-page-shadow p-3 text-center">
        <div className="flex justify-center"><CatalogIcon assetId={item.catalog_icon} spriteKey={item.sprite_key} icon={item.icon} size={40} alt={itemDisplayName(item)} /></div>
        <p className="mt-2 font-body font-semibold text-body text-ink-primary">{itemDisplayName(item)}</p>
        {profile[slot]?.id === item.id && (slot === 'active_theme'
          ? <Link className="mt-2 inline-flex min-h-11 items-center text-caption text-sheikah-teal-deep underline" to="/settings#appearance">Change color theme</Link>
          : <Button size="sm" variant="ghost" className="mt-2" disabled={working === slot} onClick={() => onRemove(slot)}>Remove previous selection</Button>)}
      </li>)}
    </ul>
  </ParchmentCard>;
}
