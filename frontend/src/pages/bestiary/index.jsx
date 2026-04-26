import ChapterHub from '../../components/layout/ChapterHub';
import Companions from './party/Companions';
import Mounts from './party/Mounts';
import BestiaryCodex from './codex/BestiaryCodex';
import Hatchery from './hatchery/Hatchery';

/**
 * Bestiary — hub page for "every creature in the journal."
 *
 * Companions (owned, growing) · Mounts (evolved, rideable) · Codex
 *   (every species, discovered or silhouetted, with lore + per-potion
 *   evolution preview) · Hatchery (hatch eggs + breed mounts; cooldown
 *   ticker + chromatic odds)
 *
 * Companions + Mounts replaced the single "Party" tab — see
 * pages/bestiary/party/. The Satchel moved to /treasury?tab=satchel.
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
      defaultTabId="companions"
      tabs={[
        { id: 'companions', label: 'Companions', render: () => <Companions /> },
        { id: 'mounts',     label: 'Mounts',     render: () => <Mounts /> },
        { id: 'codex',      label: 'Codex',      render: () => <BestiaryCodex /> },
        { id: 'hatchery',   label: 'Hatchery',   render: () => <Hatchery /> },
      ]}
    />
  );
}
