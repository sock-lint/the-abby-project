import CatalogIcon from '../../../components/rpg/CatalogIcon';

// Inventory quantities remain ingredients. Selecting a card only opens the
// existing hatch form and never consumes an egg or creates a companion.
export default function EggCollection({ eggs, potionCount, selectedId, onSelect, working }) {
  if (!eggs.length) return null;
  return (
    <section aria-label="Your eggs" className="space-y-3">
      <div>
        <h3 className="font-body text-lede font-bold text-ink-primary">Your eggs</h3>
        <p className="text-body text-ink-secondary">
          {eggs.reduce((total, entry) => total + entry.quantity, 0)} eggs in your inventory · {potionCount} hatching {potionCount === 1 ? 'potion' : 'potions'}
        </p>
      </div>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {eggs.map(({ item, quantity, available }) => {
          const content = <>
            <CatalogIcon assetId={item.catalog_icon} spriteKey={item.sprite_key} icon={item.icon || '🥚'} alt="" size={48} />
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-body text-ink-primary break-words">{item.name}</span>
              <span className="block text-caption text-ink-secondary">{available ? potionCount ? 'Choose an egg and potion' : 'Needs a potion' : 'Saved egg · unavailable for new hatching'}</span>
            </span>
            <span className="text-body font-semibold tabular-nums text-ink-primary">×{quantity}</span>
          </>;
          const className = 'w-full min-h-20 flex items-center gap-3 rounded-xl border p-3 text-left';
          return <li key={item.id}>
            {available ? <button type="button" aria-label={`Select ${item.name}`} aria-pressed={String(item.id) === selectedId}
              disabled={working} onClick={() => onSelect(String(item.id))}
              className={`${className} ${String(item.id) === selectedId ? 'border-sheikah-teal-deep bg-sheikah-teal/10' : 'border-ink-page-shadow bg-ink-page-aged'} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep disabled:opacity-50`}>
              {content}
            </button> : <div className={`${className} border-ink-page-shadow bg-ink-page-aged`}>{content}</div>}
          </li>;
        })}
      </ul>
    </section>
  );
}
