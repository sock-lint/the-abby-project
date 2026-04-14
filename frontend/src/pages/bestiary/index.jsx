import ChapterHub from '../../components/layout/ChapterHub';
import Stable from '../Stable';
import Inventory from '../Inventory';

/**
 * Bestiary — hub page for "things she has."
 *
 * Party (Stable) · Satchel (Inventory)
 *
 * Note: Sigil (Character) lives at its own route /sigil, surfaced via the
 * avatar menu in the header/sidebar — see AvatarMenu.jsx.
 */
export default function BestiaryHub() {
  return (
    <ChapterHub
      title="Bestiary"
      kicker="Chapter III · Companions & Satchels"
      glyph="dragon-crest"
      defaultTabId="party"
      tabs={[
        { id: 'party',   label: 'Party',   render: () => <Stable /> },
        { id: 'satchel', label: 'Satchel', render: () => <Inventory /> },
      ]}
    />
  );
}
