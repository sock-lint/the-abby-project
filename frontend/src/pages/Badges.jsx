import { useMemo, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { getAchievementsSummary, getBadges } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import Button from '../components/Button';
import PageShell from '../components/layout/PageShell';
import CatalogSearch from '../components/CatalogSearch';
import { useApi } from '../hooks/useApi';
import { normalizeList } from '../utils/api';
import SigilCodex from './achievements/SigilCodex';
import BadgeDetailSheet from './achievements/BadgeDetailSheet';

/**
 * Badges — the reliquary codex. Top-level sibling of Skills and Sketchbook
 * inside the Atlas hub. Pure view; parent badge CRUD still lives under
 * Skills → Manage since `ManagePanel` is one cross-cutting admin panel
 * for categories/subjects/skills/badges.
 */
export default function Badges() {
  const { data: summary, loading, error, reload } = useApi(getAchievementsSummary);
  const { data: allBadgesData, loading: badgesLoading } = useApi(getBadges);
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [filter, setFilter] = useState('');

  const allBadges = useMemo(() => normalizeList(allBadgesData), [allBadgesData]);
  const earnedBadges = useMemo(() => summary?.badges_earned || [], [summary]);
  const earnedIds = useMemo(
    () => new Set(earnedBadges.map((ub) => ub?.badge?.id).filter((x) => x != null)),
    [earnedBadges],
  );

  const q = filter.trim().toLowerCase();
  const filteredBadges = useMemo(() => {
    if (!q) return allBadges;
    return allBadges.filter((b) =>
      (b.name || '').toLowerCase().includes(q)
      || (b.description || '').toLowerCase().includes(q),
    );
  }, [allBadges, q]);
  const filteredEarned = useMemo(() => {
    if (!q) return earnedBadges;
    const filteredIds = new Set(filteredBadges.map((b) => b.id));
    return earnedBadges.filter((ub) => filteredIds.has(ub?.badge?.id));
  }, [earnedBadges, filteredBadges, q]);

  if (loading || badgesLoading) return <Loader />;
  if (error || !summary) {
    return (
      <PageShell rhythm="tight" animate={false}>
        <ErrorAlert message={error || 'Could not load the sigil case.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </PageShell>
    );
  }

  return (
    <div className="space-y-4">
      {allBadges.length > 0 && (
        <CatalogSearch
          value={filter}
          onChange={setFilter}
          placeholder="Search the reliquary…"
          ariaLabel="Filter badges"
        />
      )}

      <SigilCodex
        allBadges={filteredBadges}
        earnedBadges={filteredEarned}
        onSelect={setSelectedEntry}
      />

      <AnimatePresence>
        {selectedEntry && (
          <BadgeDetailSheet
            entry={selectedEntry}
            onClose={() => setSelectedEntry(null)}
            allBadges={allBadges}
            earnedIds={earnedIds}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
