import { useState } from 'react';
import { getAchievementsSummary, getBadges, getCategories } from '../api';
import Loader from '../components/Loader';
import TabButton from '../components/TabButton';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import { normalizeList } from '../utils/api';
import BadgeCollection from './achievements/BadgeCollection';
import ManagePanel from './achievements/ManagePanel';
import SkillTreeView from './achievements/SkillTreeView';

export default function Achievements() {
  const { isParent } = useRole();
  const { data: summary, loading } = useApi(getAchievementsSummary);
  const { data: allBadgesData, loading: badgesLoading } = useApi(getBadges);
  const { data: categoriesData, reload: reloadCategories } = useApi(getCategories);
  const [topTab, setTopTab] = useState('view');

  if (loading || badgesLoading) return <Loader />;
  if (!summary) return null;

  const categories = normalizeList(categoriesData);
  const allBadges = normalizeList(allBadgesData);
  const earnedBadges = summary.badges_earned || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Achievements</h1>
        {isParent && (
          <div className="flex gap-2">
            <TabButton active={topTab === 'view'} onClick={() => setTopTab('view')}>View</TabButton>
            <TabButton active={topTab === 'manage'} onClick={() => setTopTab('manage')}>Manage</TabButton>
          </div>
        )}
      </div>

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
