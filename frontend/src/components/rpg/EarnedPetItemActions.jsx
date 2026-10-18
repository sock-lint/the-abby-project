import { Link } from 'react-router-dom';

// Callers supply settled item outcomes, never reward previews. Old receipts
// without a type remain readable without guessing an acquisition action.
export default function EarnedPetItemActions({ items = [], onNavigate }) {
  const actions = new Map();
  for (const item of items) {
    if (!item || item.was_salvaged || item.salvaged_to_coins != null
      || (item.quantity != null && !(item.quantity > 0))) continue;
    if (['egg', 'potion'].includes(item.item_type)
      && item.item_catalog_available !== false && item.catalog_available !== false) {
      actions.set('/bestiary?tab=hatchery', 'Go to Hatchery');
    } else if (item.item_type === 'food') {
      // Saved food stays usable even when it is no longer a new catalog offer.
      actions.set('/bestiary?tab=companions', 'Feed a companion');
    }
  }
  if (!actions.size) return null;
  return <nav aria-label="Use earned pet items" className="flex flex-wrap gap-x-4">
    {[...actions].map(([to, label]) => <Link key={to} to={to} onClick={onNavigate}
      className="inline-flex min-h-11 items-center text-caption font-semibold underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded">
      {label}
    </Link>)}
  </nav>;
}
