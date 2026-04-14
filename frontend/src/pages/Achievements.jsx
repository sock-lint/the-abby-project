import { useState } from 'react';
import { getAchievementsSummary, getBadges, getCategories } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import { normalizeList } from '../utils/api';
import BadgeCollection from './achievements/BadgeCollection';
import ManagePanel from './achievements/ManagePanel';
import SkillTreeView from './achievements/SkillTreeView';

export default function Achievements() {
  const { isParent } = useRole();
  const { data: summary, loading, error, reload } = useApi(getAchievementsSummary);
  const { data: allBadgesData, loading: badgesLoading } = useApi(getBadges);
  const { data: categoriesData, reload: reloadCategories } = useApi(getCategories);
  const [topTab, setTopTab] = useState('view');

  if (loading || badgesLoading) return <Loader />;
  if (error || !summary) {
    return (
      <div className="max-w-6xl mx-auto space-y-3">
        <ErrorAlert message={error || 'Could not load the atlas.'} />
        <button
          type="button"
          onClick={reload}
          className="px-4 py-2 text-sm bg-sheikah-teal-deep text-ink-page-rune-glow rounded-lg hover:bg-sheikah-teal transition-colors font-display"
        >
          Try again
        </button>
      </div>
    );
  }

  const categories = normalizeList(categoriesData);
  const allBadges = normalizeList(allBadgesData);
  const earnedBadges = summary.badges_earned || [];

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the atlas · mastery charted in rune
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Skills &amp; Badges
          </h1>
        </div>
        {isParent && (
          <div className="flex gap-1 border border-ink-page-shadow rounded-lg p-1 bg-ink-page-aged">
            <button
              type="button"
              onClick={() => setTopTab('view')}
              className={`px-3 py-1.5 rounded font-display text-sm transition-colors ${
                topTab === 'view'
                  ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                  : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              View
            </button>
            <button
              type="button"
              onClick={() => setTopTab('manage')}
              className={`px-3 py-1.5 rounded font-display text-sm transition-colors ${
                topTab === 'manage'
                  ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                  : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              Manage
            </button>
          </div>
        )}
      </header>

      {topTab === 'manage' && isParent ? (
        <ManagePanel categories={categories} reloadCategories={reloadCategories} />
      ) : (
        <>
          <BadgeCollection allBadges={allBadges} earnedBadges={earnedBadges} />
          <SkillTreeView categories={categories} />
        </>
      )}
    </div>
  );
}
