import ChapterHub from '../../components/layout/ChapterHub';
import Stable from '../Stable';
import Character from '../Character';
import Inventory from '../Inventory';

/**
 * Bestiary — hub page for "things she has."
 *
 * Party (Stable) · Sigil (Character) · Satchel (Inventory)
 */
export default function BestiaryHub() {
  return (
    <ChapterHub
      title="Bestiary"
      kicker="Chapter III · Companions, Sigils & Satchels"
      glyph="dragon-crest"
      defaultTabId="party"
      tabs={[
        { id: 'party',   label: 'Party',   render: () => <Stable /> },
        { id: 'sigil',   label: 'Sigil',   render: () => <Character /> },
        { id: 'satchel', label: 'Satchel', render: () => <Inventory /> },
      ]}
    />
  );
}
