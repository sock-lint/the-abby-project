import { AnimatePresence } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import EmptyState from '../../components/EmptyState';
import TomeShelf from '../../components/atlas/TomeShelf';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import EconomyDiagram from './EconomyDiagram';
import EntryDetailSheet from './EntryDetailSheet';
import LorebookFolio from './LorebookFolio';
import LorebookIncipit from './LorebookIncipit';
import { groupEntriesByChapter } from './lorebook.constants';
import TrialSheet from './trials/TrialSheet';

const STORAGE_KEY = 'atlas:lorebook-codex:active-chapter';

/**
 * LorebookCodex — incipit hero, then a TomeShelf of chapter spines opening
 * onto ONE LorebookFolio at a time. Same shelf+single-folio shape as its
 * Atlas siblings (SigilCodex on Badges, BestiaryCodex): a kid who learns
 * "pull a tome, read its folio" on one tab gets the same interaction here
 * instead of a single stacked scroll of every chapter.
 */
export default function LorebookCodex({
  entries = [],
  mode = 'kid',
  parentPanelsDefaultOpen = false,
  showEconomyDiagram = false,
  onTrained,
}) {
  const [detailEntry, setDetailEntry] = useState(null);
  const [trialEntry, setTrialEntry] = useState(null);
  // User-clicked chapter override, seeded from localStorage. The effective
  // active chapter is derived below so it self-heals if the remembered
  // chapter stops existing (content edit) or empties out.
  const [override, setOverride] = useState(() => {
    try {
      return window.localStorage?.getItem(STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });
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
      // Open the shelf on the chapter the deep-linked entry lives in, so
      // closing the trial leaves the kid looking at the right folio.
      if (target.chapter) setOverride(target.chapter);
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

  // Priority: (1) remembered chapter that still holds entries, (2) first
  // chapter that holds any, (3) first chapter overall.
  const activeChapterId = useMemo(() => {
    const remembered = grouped.find((c) => c.chapter.id === override);
    if (remembered && remembered.total > 0) return remembered.chapter.id;
    const populated = grouped.find((c) => c.total > 0);
    return populated?.chapter.id ?? grouped[0]?.chapter.id ?? null;
  }, [grouped, override]);

  const selectChapter = (id) => {
    setOverride(id);
    try {
      window.localStorage?.setItem(STORAGE_KEY, id);
    } catch {
      // ignore quota / disabled storage
    }
  };

  const shelfItems = useMemo(
    () =>
      grouped.map((chapter) => {
        const pct = chapter.total ? (chapter.trained / chapter.total) * 100 : 0;
        return {
          id: chapter.chapter.id,
          name: chapter.chapter.name,
          icon: chapter.chapter.letter,
          chip: `${chapter.trained}/${chapter.total}`,
          progressPct: pct,
          tier: tierForProgress({ unlocked: true, progressPct: pct, level: 0 }),
          ariaLabel: `${chapter.chapter.name}, ${chapter.trained} of ${chapter.total} inked`,
        };
      }),
    [grouped],
  );

  const activeChapter =
    grouped.find((c) => c.chapter.id === activeChapterId) ?? grouped[0];

  if (!entries.length) {
    return <EmptyState>The Lorebook has not been inked yet.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <LorebookIncipit unlocked={unlocked} trained={trained} total={total} mode={mode} />

      {showEconomyDiagram && <EconomyDiagram entries={entries} />}

      <TomeShelf
        items={shelfItems}
        activeId={activeChapterId}
        onSelect={selectChapter}
        ariaLabel="Lorebook chapters"
      />

      {activeChapter && (
        <LorebookFolio
          key={activeChapter.chapter.id}
          chapter={activeChapter.chapter}
          entries={activeChapter.entries}
          unlocked={activeChapter.unlocked}
          trained={activeChapter.trained}
          total={activeChapter.total}
          onSelect={handleSelect}
        />
      )}

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
