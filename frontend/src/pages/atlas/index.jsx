import ChapterHub from '../../components/layout/ChapterHub';
import Achievements from '../Achievements';
import Badges from '../Badges';
import Portfolio from '../Portfolio';

/**
 * Atlas — hub page for "what she's accomplished."
 *
 * Skills (illuminated skill tree) · Badges (wax-seal sigils) · Sketchbook
 * (photos + proofs). Manage (parent CRUD for categories/subjects/skills/
 * badges) lives under Skills since ManagePanel is one cross-cutting panel.
 */
export default function AtlasHub() {
  return (
    <ChapterHub
      title="Atlas"
      kicker="Chapter V · The Cartography of Mastery"
      glyph="compass-rose"
      defaultTabId="skills"
      tabs={[
        { id: 'skills',     label: 'Skills',     render: () => <Achievements /> },
        { id: 'badges',     label: 'Badges',     render: () => <Badges /> },
        { id: 'sketchbook', label: 'Sketchbook', render: () => <Portfolio /> },
      ]}
    />
  );
}
