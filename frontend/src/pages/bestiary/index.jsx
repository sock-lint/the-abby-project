import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import ChapterHub from '../../components/layout/ChapterHub';
import Companions from './party/Companions';
import Mounts from './party/Mounts';
import BestiaryCodex from './codex/BestiaryCodex';
import Hatchery from './hatchery/Hatchery';
import { useRole } from '../../hooks/useRole';

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
  const { user } = useRole();
  return (
    <>
      <ChapterHub
        key={user?.id}
        title="Pets"
        kicker="Care for companions and grow your collection"
        glyph="dragon-crest"
        defaultTabId="companions"
        tabs={[
          { id: 'companions', label: 'Companions', render: () => <Companions /> },
          { id: 'mounts',     label: 'Mounts',     render: () => <Mounts /> },
          { id: 'codex',      label: 'Collection', render: () => <BestiaryCodex /> },
          { id: 'hatchery',   label: 'Hatching',   render: () => <Hatchery /> },
        ]}
      />
      <div className="max-w-6xl mx-auto mt-4 text-right">
        <Link to="/sigil" className="inline-flex items-center min-h-11 mr-6 font-semibold text-caption text-sheikah-teal-deep">My profile <ArrowRight size={14} aria-hidden="true" /></Link>
        <Link to="/treasury?tab=satchel" className="inline-flex items-center min-h-11 mr-6 font-semibold text-caption text-sheikah-teal-deep">Inventory <ArrowRight size={14} aria-hidden="true" /></Link>
        <Link
          to="/atlas"
          className="inline-flex items-center gap-1.5 font-script text-caption text-ink-whisper hover:text-sheikah-teal-deep transition-colors"
        >
          Skills, badges & help <ArrowRight size={14} />
        </Link>
      </div>
    </>
  );
}
