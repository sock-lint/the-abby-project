import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { getAchievementsSummary, getBadges } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import { useApi } from '../hooks/useApi';
import { normalizeList } from '../utils/api';
import BadgeSigilGrid from './achievements/BadgeSigilGrid';
import BadgeDetailSheet from './achievements/BadgeDetailSheet';

/**
 * Badges — the sigil case. Top-level sibling of Skills and Sketchbook
 * inside the Atlas hub. Pure view; parent badge CRUD still lives under
 * Skills → Manage since `ManagePanel` is one cross-cutting admin panel
 * for categories/subjects/skills/badges.
 */
export default function Badges() {
  const { data: summary, loading, error, reload } = useApi(getAchievementsSummary);
  const { data: allBadgesData, loading: badgesLoading } = useApi(getBadges);
  const [selectedEntry, setSelectedEntry] = useState(null);

  if (loading || badgesLoading) return <Loader />;
  if (error || !summary) {
    return (
      <div className="max-w-6xl mx-auto space-y-3">
        <ErrorAlert message={error || 'Could not load the sigil case.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  const allBadges = normalizeList(allBadgesData);
  const earnedBadges = summary.badges_earned || [];

  return (
    <div className="space-y-4">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          the sigil case · wax seals of mastery
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Badges
        </h1>
        <p className="mt-1 text-caption text-ink-whisper font-script">
          {earnedBadges.length} of {allBadges.length} sealed
        </p>
      </header>

      <BadgeSigilGrid
        allBadges={allBadges}
        earnedBadges={earnedBadges}
        onSelect={setSelectedEntry}
      />

      <AnimatePresence>
        {selectedEntry && (
          <BadgeDetailSheet entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}
