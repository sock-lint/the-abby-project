import { AnimatePresence } from 'framer-motion';
import { useMemo, useState } from 'react';
import EmptyState from '../../components/EmptyState';
import EconomyDiagram from './EconomyDiagram';
import EntryDetailSheet from './EntryDetailSheet';
import LorebookFolio from './LorebookFolio';
import LorebookIncipit from './LorebookIncipit';
import { groupEntriesByChapter } from './lorebook.constants';

export default function LorebookCodex({
  entries = [],
  mode = 'kid',
  parentPanelsDefaultOpen = false,
  showEconomyDiagram = false,
}) {
  const [selectedEntry, setSelectedEntry] = useState(null);
  const grouped = useMemo(() => groupEntriesByChapter(entries), [entries]);
  const total = entries.length;
  const unlocked = entries.filter((entry) => entry.unlocked).length;

  if (!entries.length) {
    return <EmptyState>The Lorebook has not been inked yet.</EmptyState>;
  }

  return (
    <div className="space-y-5">
      <LorebookIncipit unlocked={unlocked} total={total} mode={mode} />

      {showEconomyDiagram && <EconomyDiagram entries={entries} />}

      <div className="space-y-4">
        {grouped.map((chapter) => (
          <LorebookFolio
            key={chapter.chapter.id}
            chapter={chapter.chapter}
            entries={chapter.entries}
            unlocked={chapter.unlocked}
            total={chapter.total}
            onSelect={setSelectedEntry}
          />
        ))}
      </div>

      <AnimatePresence>
        {selectedEntry && (
          <EntryDetailSheet
            entry={selectedEntry}
            mode={mode}
            parentPanelsDefaultOpen={parentPanelsDefaultOpen}
            onClose={() => setSelectedEntry(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
