import ChapterHub from '../../components/layout/ChapterHub';
import Achievements from '../Achievements';
import Portfolio from '../Portfolio';

/**
 * Atlas — hub page for "what she's accomplished."
 *
 * Skills (skill tree + achievements) · Sketchbook (photos + proofs)
 *
 * Phase 5 will split Skills from Badges into distinct tabs and redesign
 * the skill tree as a Sheikah map.
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
        { id: 'sketchbook', label: 'Sketchbook', render: () => <Portfolio /> },
      ]}
    />
  );
}
