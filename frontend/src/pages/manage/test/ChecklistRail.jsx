import { useMemo, useState } from 'react';
import { ScrollText, Eraser } from 'lucide-react';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import Button from '../../../components/Button';
import Loader from '../../../components/Loader';
import { devToolsChecklist } from '../../../api';
import { useApi } from '../../../hooks/useApi';

const STORAGE_KEY = 'manage:test:checklist:v1';

/**
 * Parses docs/manual-testing.md into row entries we can check off.
 *
 * The doc uses GitHub-flavored markdown tables. Each `| ... |` row in a
 * table body becomes a checklist item. The first cell is the surface
 * label; we keep the rest as supporting text in the title attribute so
 * a hover reveals the precondition + how-to-trigger + verify columns.
 */
function parseChecklist(markdown) {
  if (!markdown) return [];
  const lines = markdown.split(/\r?\n/);
  const out = [];
  let currentSection = '';
  let inTable = false;
  let pastHeaderSep = false;

  for (const raw of lines) {
    const line = raw.trimEnd();
    const headingMatch = /^##\s+(.+)$/.exec(line);
    if (headingMatch) {
      currentSection = headingMatch[1].trim();
      inTable = false;
      pastHeaderSep = false;
      continue;
    }
    if (!line.startsWith('|')) {
      inTable = false;
      pastHeaderSep = false;
      continue;
    }
    // Found a table line. The first one is the header, the second is
    // the |---|---| separator, anything after is data.
    if (!inTable) {
      inTable = true;
      pastHeaderSep = false;
      continue;
    }
    if (!pastHeaderSep) {
      pastHeaderSep = /^\s*\|\s*-/.test(line);
      continue;
    }
    const cells = line
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((c) => c.trim());
    if (cells.length === 0 || !cells[0]) continue;
    const id = `${currentSection}::${cells[0]}::${cells.length}`.slice(0, 200);
    out.push({
      id,
      section: currentSection,
      label: cells[0],
      meta: cells.slice(1).filter(Boolean).join(' · '),
    });
  }
  return out;
}

function loadChecks() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveChecks(set) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    /* quota exceeded — silent */
  }
}

export default function ChecklistRail() {
  const { data, loading } = useApi(devToolsChecklist);
  const [checked, setChecked] = useState(() => loadChecks());

  const markdown = data?.markdown || '';
  const items = useMemo(() => parseChecklist(markdown), [markdown]);
  const grouped = useMemo(() => {
    const map = new Map();
    for (const item of items) {
      if (!map.has(item.section)) map.set(item.section, []);
      map.get(item.section).push(item);
    }
    return [...map.entries()];
  }, [items]);

  const toggle = (id) => {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setChecked(next);
    saveChecks(next);
  };

  const clearAll = () => {
    setChecked(new Set());
    saveChecks(new Set());
  };

  const total = items.length;
  const done = items.filter((i) => checked.has(i.id)).length;

  return (
    <ParchmentCard className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display italic text-lg text-ink-primary flex items-center gap-2">
          <ScrollText size={16} /> Checklist
        </h3>
        <span className="text-caption text-ink-secondary font-script">
          {done} / {total}
        </span>
      </div>

      {loading ? (
        <Loader />
      ) : items.length === 0 ? (
        <p className="text-caption text-ink-secondary italic">
          docs/manual-testing.md is empty or not bundled.
        </p>
      ) : (
        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          {grouped.map(([section, rows]) => (
            <div key={section}>
              <div className="font-script text-caption text-sheikah-teal-deep sticky top-0 bg-ink-page-aged py-1">
                {section}
              </div>
              <ul className="space-y-1 mt-1">
                {rows.map((row) => (
                  <li key={row.id} className="flex items-start gap-2 text-caption">
                    <input
                      type="checkbox"
                      checked={checked.has(row.id)}
                      onChange={() => toggle(row.id)}
                      aria-label={`${row.section} — ${row.label}`}
                      className="mt-0.5 cursor-pointer accent-sheikah-teal-deep"
                    />
                    <span
                      className={
                        checked.has(row.id)
                          ? 'line-through text-ink-secondary'
                          : 'text-ink-primary'
                      }
                      title={row.meta}
                    >
                      {row.label}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {total > 0 ? (
        <div className="flex justify-end pt-2 border-t border-ink-page-shadow">
          <Button
            variant="ghost"
            size="sm"
            onClick={clearAll}
            className="flex items-center gap-1"
          >
            <Eraser size={12} /> Clear
          </Button>
        </div>
      ) : null}
    </ParchmentCard>
  );
}
