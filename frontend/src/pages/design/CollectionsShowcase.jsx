import { useId, useState } from 'react';
import TomeShelf from '../../components/atlas/TomeShelf';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import { BADGE_COLLECTIONS, INVENTORY_FILTERS, INVENTORY_ITEMS, LOREBOOK_TOPICS } from './showcase.fixtures';

export default function CollectionsShowcase() {
  const titleId = useId();
  const badgePanelId = useId();
  const lorePanelId = useId();
  const filterPanelId = useId();
  const [badgeId, setBadgeId] = useState(BADGE_COLLECTIONS[0].id);
  const [loreId, setLoreId] = useState(LOREBOOK_TOPICS[0].id);
  const [filterId, setFilterId] = useState('all');
  const badgeCollection = BADGE_COLLECTIONS.find((entry) => entry.id === badgeId);
  const loreTopic = LOREBOOK_TOPICS.find((entry) => entry.id === loreId);
  const activeFilter = INVENTORY_FILTERS.find((entry) => entry.id === filterId);
  const filteredInventory = INVENTORY_ITEMS.filter((entry) => filterId === 'all' || entry.kind === filterId);

  const badgeItems = BADGE_COLLECTIONS.map((collection) => {
    const earned = collection.entries.filter((entry) => entry.earned).length;
    const total = collection.entries.length;
    const progressPct = (earned / total) * 100;
    return { id: collection.id, name: collection.name, icon: collection.icon,
      chip: `${earned} / ${total}`, progressPct, tier: tierForProgress({ unlocked: true, progressPct }),
      ariaLabel: `${collection.name}, ${earned} of ${total} badges earned` };
  });
  const loreItems = LOREBOOK_TOPICS.map((topic) => ({ id: topic.id, name: topic.name, icon: topic.icon,
    chip: `${topic.entries.length} entries`, ariaLabel: `${topic.name}, ${topic.entries.length} entries` }));
  const filterItems = INVENTORY_FILTERS.map((filter) => {
    const count = INVENTORY_ITEMS.filter((entry) => filter.id === 'all' || entry.kind === filter.id)
      .reduce((sum, entry) => sum + entry.quantity, 0);
    return { ...filter, variant: 'vessel', chip: count, ariaLabel: `${filter.name}, ${count} items` };
  });

  return <section id="collections" aria-labelledby={titleId} className="space-y-6">
    <header className="space-y-2">
      <h2 id={titleId} className="font-display text-2xl font-bold text-ink-primary">Collection navigation</h2>
      <p className="font-body text-body text-ink-secondary max-w-prose">
        Synthetic Badges, Lorebook, and Satchel examples. Readable collection cards
        and compact filter pills wrap to fit the page. Choose a collection or filter
        to preview its contents below.
      </p>
    </header>

    <ParchmentCard tone="bright" className="space-y-4">
      <header className="space-y-1">
        <h3 className="font-display font-semibold text-xl text-ink-primary">Badge collections</h3>
        <p className="text-caption text-ink-secondary">Count chips show earned / total badges. The bar shows the same earned share.</p>
      </header>
      <TomeShelf items={badgeItems} activeId={badgeId} onSelect={setBadgeId} ariaLabel="Demo badge collections" />
      <section aria-labelledby={badgePanelId} className="space-y-3">
        <h4 id={badgePanelId} className="font-display font-semibold text-lede text-ink-primary">{badgeCollection.name}</h4>
        <p className="text-body text-ink-secondary">{badgeCollection.description}</p>
        <ul className="space-y-2">
          {badgeCollection.entries.map((entry) => <li key={entry.name} className="flex items-center justify-between flex-wrap gap-2 rounded-lg bg-ink-page-aged px-3 py-2">
            <span className="font-body text-body text-ink-primary">{entry.name}</span>
            <RuneBadge tone={entry.earned ? 'moss' : 'ink'}>{entry.earned ? 'Earned' : 'Not yet earned'}</RuneBadge>
          </li>)}
        </ul>
      </section>
    </ParchmentCard>

    <ParchmentCard tone="bright" className="space-y-4">
      <header className="space-y-1">
        <h3 className="font-display font-semibold text-xl text-ink-primary">Lorebook topics</h3>
        <p className="text-caption text-ink-secondary">Entry counts describe available reading. Long names stay readable.</p>
      </header>
      <TomeShelf items={loreItems} activeId={loreId} onSelect={setLoreId} ariaLabel="Demo Lorebook topics" />
      <section aria-labelledby={lorePanelId} className="space-y-3">
        <h4 id={lorePanelId} className="font-display font-semibold text-lede text-ink-primary">{loreTopic.name}</h4>
        <ul className="space-y-2">
          {loreTopic.entries.map((entry) => <li key={entry} className="rounded-lg bg-ink-page-aged px-3 py-2 text-body text-ink-primary">{entry}</li>)}
        </ul>
      </section>
    </ParchmentCard>

    <ParchmentCard tone="bright" className="space-y-4">
      <header className="space-y-1">
        <h3 className="font-display font-semibold text-xl text-ink-primary">Satchel filters</h3>
        <p className="text-caption text-ink-secondary">Compact pills use the same selection controls at every width. Counts show sample quantities.</p>
      </header>
      <TomeShelf items={filterItems} activeId={filterId} onSelect={setFilterId} ariaLabel="Demo Satchel filters" />
      <section aria-labelledby={filterPanelId} className="space-y-3">
        <h4 id={filterPanelId} className="font-display font-semibold text-lede text-ink-primary">{activeFilter.name}</h4>
        <ul className="space-y-2">
          {filteredInventory.map((entry) => <li key={entry.id} className="flex items-center justify-between gap-3 rounded-lg bg-ink-page-aged px-3 py-2">
            <span className="font-body text-body text-ink-primary">{entry.name}</span>
            <RuneBadge tone="teal">×{entry.quantity}</RuneBadge>
          </li>)}
        </ul>
      </section>
    </ParchmentCard>
  </section>;
}
