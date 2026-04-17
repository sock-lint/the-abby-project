import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import { getAchievementsSummary, getBadges, getCategories } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import { normalizeList } from '../utils/api';
import BadgeSigilGrid from './achievements/BadgeSigilGrid';
import BadgeDetailSheet from './achievements/BadgeDetailSheet';
import ManagePanel from './achievements/ManagePanel';
import SkillTreeView from './achievements/SkillTreeView';

const VIEW_TABS = [
  { id: 'atlas', label: 'Atlas', hint: 'the skill tree' },
  { id: 'sigils', label: 'Sigils', hint: 'your badge haul' },
];

function normalizeViewTab(raw) {
  return VIEW_TABS.some((t) => t.id === raw) ? raw : 'atlas';
}

export default function Achievements() {
  const { isParent } = useRole();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: summary, loading, error, reload } = useApi(getAchievementsSummary);
  const { data: allBadgesData, loading: badgesLoading } = useApi(getBadges);
  const { data: categoriesData, reload: reloadCategories } = useApi(getCategories);
  const [topTab, setTopTab] = useState('view');
  const [selectedEntry, setSelectedEntry] = useState(null);

  const viewTab = normalizeViewTab(searchParams.get('tab'));

  const setViewTab = (id) => {
    const params = new URLSearchParams(searchParams);
    if (id === 'atlas') params.delete('tab');
    else params.set('tab', id);
    setSearchParams(params, { replace: false });
  };

  if (loading || badgesLoading) return <Loader />;
  if (error || !summary) {
    return (
      <div className="max-w-6xl mx-auto space-y-3">
        <ErrorAlert message={error || 'Could not load the atlas.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
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
        <>
          {/* Sub-tab row: Atlas | Sigils. Stays under the header, above either view. */}
          <div
            role="tablist"
            aria-label="Achievements view"
            className="inline-flex items-center gap-1 border border-ink-page-shadow rounded-xl p-1 bg-ink-page-aged shadow-[0_1px_0_0_var(--color-ink-page-rune-glow)_inset]"
          >
            {VIEW_TABS.map((tab) => {
              const active = viewTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active ? 'true' : 'false'}
                  onClick={() => setViewTab(tab.id)}
                  className={`px-4 py-2 min-h-[40px] rounded-lg font-display text-sm transition-colors ${
                    active
                      ? 'bg-sheikah-teal-deep text-ink-page-rune-glow shadow-[0_1px_0_0_var(--color-gold-leaf)]'
                      : 'text-ink-secondary hover:text-ink-primary'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {viewTab === 'atlas' ? (
            <SkillTreeView categories={categories} />
          ) : (
            <section>
              <h2 className="font-display italic text-lede md:text-xl text-ink-primary mb-3">
                {earnedBadges.length} of {allBadges.length} sigils sealed
              </h2>
              <BadgeSigilGrid
                allBadges={allBadges}
                earnedBadges={earnedBadges}
                onSelect={setSelectedEntry}
              />
            </section>
          )}
        </>
      )}

      <AnimatePresence>
        {selectedEntry && (
          <BadgeDetailSheet entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

function TopTabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active ? 'true' : 'false'}
      onClick={onClick}
      className={`px-3 py-1.5 rounded font-display text-sm transition-colors ${
        active
          ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
          : 'text-ink-secondary hover:text-ink-primary'
      }`}
    >
      {children}
    </button>
  );
}
