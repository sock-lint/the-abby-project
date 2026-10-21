import { useState } from 'react';
import { getAllCategories } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import PageShell from '../components/layout/PageShell';
import TabList from '../components/layout/TabList';
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
  const { isParent, user } = useRole();
  const {
    data: categoriesData, loading, error, reload: reloadCategories,
  } = useApi((signal) => getAllCategories({ includeRetired: true, signal }));
  const [topTab, setTopTab] = useState('view');

  if (loading) return <Loader />;
  if (error || !categoriesData) {
    return (
      <PageShell rhythm="tight" animate={false}>
        <ErrorAlert message={error || 'Could not load skills.'} />
        <Button variant="primary" onClick={reloadCategories}>
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
            Track your skill progress
          </div>
          {/* Below md the Atlas hub's tab strip already names this page —
              the stacked h1 + explainer ate ~100px above the fold on phones. */}
          <h1 className="sr-only md:not-sr-only font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Skills
          </h1>
          <div className="hidden md:block font-script text-body text-ink-whisper mt-1 max-w-xl">
            Build skills through project work, approved chores and homework, habits, challenges, and journal entries.
          </div>
        </div>
        {isParent && (
          <TabList
            tabs={[{ id: 'view', label: 'View' }, { id: 'manage', label: 'Manage' }]}
            activeId={topTab}
            onSelect={setTopTab}
            variant="pill"
            ariaLabel="Skills mode"
          />
        )}
      </header>

      {topTab === 'manage' && isParent ? (
        <ManagePanel categories={categories} reloadCategories={reloadCategories} canManageTaxonomy={Boolean(user?.is_staff)} />
      ) : (
        <SkillTreeView categories={categories} />
      )}
    </div>
  );
}
