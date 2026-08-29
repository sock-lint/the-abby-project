import { useState } from 'react';
import { getAchievementsSummary, getCategories } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import PageShell from '../components/layout/PageShell';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import { normalizeList } from '../utils/api';
import ManagePanel from './achievements/ManagePanel';
import SkillTreeView from './achievements/SkillTreeView';

/**
 * Achievements — the skill tree / "Illuminated Atlas" page.
 *
 * Pure skills view for children. Parents also see a View | Manage toggle;
 * Manage hosts CRUD for categories/subjects/skills/badges (badges live on
 * their own top-level sibling page but admin for them stays co-located
 * here because ManagePanel is a single cross-cutting admin surface).
 */
export default function Achievements() {
  const { isParent } = useRole();
  const { data: summary, loading, error, reload } = useApi(getAchievementsSummary);
  const { data: categoriesData, reload: reloadCategories } = useApi(getCategories);
  const [topTab, setTopTab] = useState('view');

  if (loading) return <Loader />;
  if (error || !summary) {
    return (
      <PageShell rhythm="tight" animate={false}>
        <ErrorAlert message={error || 'Could not load the atlas.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </PageShell>
    );
  }

  const categories = normalizeList(categoriesData);

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the atlas · mastery charted in rune
          </div>
          {/* Below md the Atlas hub's tab strip already names this page —
              the stacked h1 + explainer ate ~100px above the fold on phones. */}
          <h1 className="hidden md:block font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Skills
          </h1>
          <div className="hidden md:block font-script text-body text-ink-whisper mt-1 max-w-xl">
            skills grow from clocked ventures, approved duties, study, rituals, quests, and journal entries
          </div>
        </div>
        {isParent && (
          <div
            role="tablist"
            aria-label="Achievements mode"
            className="flex gap-1 border border-ink-page-shadow rounded-lg p-1 bg-ink-page-aged"
          >
            <TopTabButton active={topTab === 'view'} onClick={() => setTopTab('view')}>
              View
            </TopTabButton>
            <TopTabButton active={topTab === 'manage'} onClick={() => setTopTab('manage')}>
              Manage
            </TopTabButton>
          </div>
        )}
      </header>

      {topTab === 'manage' && isParent ? (
        <ManagePanel categories={categories} reloadCategories={reloadCategories} />
      ) : (
        <SkillTreeView categories={categories} />
      )}
    </div>
  );
}

/**
 * Parent-only View | Manage pill. Speaks TabList's `pill` vocabulary
 * (aged-parchment tray, teal-filled active pill, font-display text-body) but
 * stays local so each pill can carry the app's 44px `min-h-11` touch floor —
 * TabList's shared pill tops out around 36px and lives outside this page.
 */
function TopTabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active ? 'true' : 'false'}
      onClick={onClick}
      className={`min-h-11 px-3 py-2 rounded-md font-display text-body transition-colors ${
        active
          ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
          : 'text-ink-secondary hover:text-ink-primary'
      }`}
    >
      {children}
    </button>
  );
}
