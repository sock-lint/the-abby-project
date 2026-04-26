import { Navigate, useSearchParams } from 'react-router-dom';
import ChapterHub from '../../components/layout/ChapterHub';
import Achievements from '../Achievements';
import Badges from '../Badges';
import Lorebook from '../Lorebook';

/**
 * Atlas — hub page for "what she's accomplished."
 *
 * Skills (illuminated skill tree) · Badges (wax-seal sigils) · Lorebook
 * (world-building reference). Manage (parent CRUD for categories/subjects/
 * skills/badges) lives under Skills since ManagePanel is one cross-cutting
 * panel.
 *
 * Sketchbook + Yearbook moved to Chapter VI — Chronicle (the autobiography
 * surface). Atlas is the résumé; Chronicle is the memoir. Bookmarks of
 * `/atlas?tab=sketchbook` and `/atlas?tab=yearbook` redirect to the new
 * tab inside Chronicle.
 */
const LEGACY_TAB_REDIRECTS = {
  sketchbook: '/chronicle?tab=sketchbook',
  yearbook: '/chronicle?tab=yearbook',
};

export default function AtlasHub() {
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  if (requestedTab && LEGACY_TAB_REDIRECTS[requestedTab]) {
    return <Navigate to={LEGACY_TAB_REDIRECTS[requestedTab]} replace />;
  }

  return (
    <ChapterHub
      title="Atlas"
      kicker="Chapter V · The Cartography of Mastery"
      glyph="compass-rose"
      defaultTabId="skills"
      tabs={[
        { id: 'skills',   label: 'Skills',   render: () => <Achievements /> },
        { id: 'badges',   label: 'Badges',   render: () => <Badges /> },
        { id: 'lorebook', label: 'Lorebook', render: () => <Lorebook /> },
      ]}
    />
  );
}
