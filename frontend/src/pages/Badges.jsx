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
import BadgeSigil from '../components/atlas/BadgeSigil';
import { isCatalogAvailable } from '../utils/catalogAvailability';

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

  const allBadges = useMemo(() => normalizeList(allBadgesData).filter(isCatalogAvailable), [allBadgesData]);
  const earnedBadges = useMemo(() => summary?.badges_earned || [], [summary]);
  const savedBadges = earnedBadges.filter((entry) => !isCatalogAvailable(entry.badge));
  const currentEarned = useMemo(() => earnedBadges.filter((entry) => isCatalogAvailable(entry.badge)), [earnedBadges]);
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
    if (!q) return currentEarned;
    const filteredIds = new Set(filteredBadges.map((b) => b.id));
    return currentEarned.filter((ub) => filteredIds.has(ub?.badge?.id));
  }, [currentEarned, filteredBadges, q]);

  if (loading || badgesLoading) return <Loader />;
  if (error || !summary) {
    return (
      <PageShell rhythm="tight" animate={false}>
        <ErrorAlert message={error || 'Could not load badges.'} />
        <Button variant="primary" onClick={reload}>
          Try again
        </Button>
      </PageShell>
    );
  }

  // space-y-5 is the shared hub-tab-body rhythm (PageShell's `default`
  // tier) — sibling Atlas tabs used to each pick their own, so switching
  // tabs inside one hub visibly changed section spacing.
  return (
    <div className="space-y-5">
      {(allBadges.length > 0 || savedBadges.length > 0) && (
        <CatalogSearch
          value={filter}
          onChange={setFilter}
          placeholder="Search badges…"
          ariaLabel="Filter badges"
        />
      )}

      <SigilCodex
        allBadges={filteredBadges}
        earnedBadges={filteredEarned}
        onSelect={setSelectedEntry}
      />

      {savedBadges.length > 0 && <section className="space-y-3" aria-label="Saved collection">
        <div><h2 className="font-body font-bold text-lede text-ink-primary">Saved collection</h2>
          <p className="font-body text-caption text-ink-secondary">Your earlier earned badges stay yours.</p></div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {savedBadges.filter((entry) => !q || `${entry.badge.name} ${entry.badge.description || ''}`.toLowerCase().includes(q)).map((entry) => <BadgeSigil key={entry.badge.id} badge={entry.badge} earned earnedAt={entry.earned_at} onSelect={setSelectedEntry} />)}
        </div>
      </section>}

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
