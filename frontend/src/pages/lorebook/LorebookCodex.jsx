import { AnimatePresence } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import EmptyState from '../../components/EmptyState';
import EconomyDiagram from './EconomyDiagram';
import EntryDetailSheet from './EntryDetailSheet';
import LorebookFolio from './LorebookFolio';
import LorebookIncipit from './LorebookIncipit';
import { groupEntriesByChapter } from './lorebook.constants';
import TrialSheet from './trials/TrialSheet';

export default function LorebookCodex({
  entries = [],
  mode = 'kid',
  parentPanelsDefaultOpen = false,
  showEconomyDiagram = false,
  onTrained,
}) {
  const [detailEntry, setDetailEntry] = useState(null);
  const [trialEntry, setTrialEntry] = useState(null);
  const grouped = useMemo(() => groupEntriesByChapter(entries), [entries]);
  const total = entries.length;
  const unlocked = entries.filter((entry) => entry.unlocked).length;
  const trained = entries.filter((entry) => entry.trained).length;
  const location = useLocation();
  const navigate = useNavigate();

  // Deep-link from FirstEncounterSheet: ?trial=<slug> auto-opens that trial.
  // Idempotent: once the param is stripped, subsequent runs find no slug
  // and return early, so depending on the full location.search + entries
  // array is safe — and prevents the prior bug where a navigation that
  // arrived before entries finished loading would silently miss the trial.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const slug = params.get('trial');
    if (!slug) return;
    const target = entries.find((e) => e.slug === slug);
    if (target && target.unlocked && !target.trained) {
      setTrialEntry(target);
    }
    // Strip the param so a refresh doesn't re-trigger.
    params.delete('trial');
    navigate(
      { pathname: location.pathname, search: params.toString() },
      { replace: true },
    );
  }, [entries, location.pathname, location.search, navigate]);

  const handleSelect = (entry, selectMode) => {
    if (selectMode === 'trial') setTrialEntry(entry);
    else if (selectMode === 'detail') setDetailEntry(entry);
  };

  if (!entries.length) {
    return <EmptyState>The Lorebook has not been inked yet.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <LorebookIncipit unlocked={unlocked} trained={trained} total={total} mode={mode} />

      {showEconomyDiagram && <EconomyDiagram entries={entries} />}

      <div className="space-y-4">
        {grouped.map((chapter) => (
          <LorebookFolio
            key={chapter.chapter.id}
            chapter={chapter.chapter}
            entries={chapter.entries}
            unlocked={chapter.unlocked}
            trained={chapter.trained}
            total={chapter.total}
            onSelect={handleSelect}
          />
        ))}
      </div>

      <AnimatePresence>
        {detailEntry && (
          <EntryDetailSheet
            entry={detailEntry}
            mode={mode}
            parentPanelsDefaultOpen={parentPanelsDefaultOpen}
            onClose={() => setDetailEntry(null)}
          />
        )}
        {trialEntry && (
          <TrialSheet
            entry={trialEntry}
            onClose={() => setTrialEntry(null)}
            onTrained={(slug) => {
              onTrained?.(slug);
              setTrialEntry(null);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
