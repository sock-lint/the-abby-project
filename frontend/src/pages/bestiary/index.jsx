import ChapterHub from '../../components/layout/ChapterHub';
import Stable from '../Stable';
import BestiaryCodex from './codex/BestiaryCodex';
import Hatchery from './hatchery/Hatchery';

/**
 * Bestiary — hub page for "every creature in the journal."
 *
 * Party (Stable — owned companions + mounts) · Codex (every species,
 *   discovered or silhouetted, with lore + per-potion evolution preview)
 *   · Hatchery (hatch eggs + breed mounts; cooldown ticker + chromatic odds)
 *
 * The Satchel moved to /treasury?tab=satchel — see TreasuryHub.
 *
 * Note: Sigil (Character) lives at its own route /sigil, surfaced via the
 * avatar menu in the header/sidebar — see AvatarMenu.jsx.
 */
export default function BestiaryHub() {
  return (
    <ChapterHub
      title="Bestiary"
      kicker="Chapter III · Creatures, Codex & Hatchery"
      glyph="dragon-crest"
      defaultTabId="party"
      tabs={[
        { id: 'party',    label: 'Party',    render: () => <Stable /> },
        { id: 'codex',    label: 'Codex',    render: () => <BestiaryCodex /> },
        { id: 'hatchery', label: 'Hatchery', render: () => <Hatchery /> },
      ]}
    />
  );
}
