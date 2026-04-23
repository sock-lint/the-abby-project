import { useMemo, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import Button from '../../components/Button';
import EmptyState from '../../components/EmptyState';
import RpgSprite from '../../components/rpg/RpgSprite';

function groupByPack(list) {
  return list.reduce((acc, s) => {
    (acc[s.pack] ||= []).push(s);
    return acc;
  }, {});
}

/**
 * SpritesBlock — parent-only master catalog of every registered sprite.
 *
 * Renders a search box + "Create sprite" button above a grouped grid
 * (one section per pack). Clicking a tile fires `onSelect(sprite)` so the
 * parent CodexSection can open the SpriteDetailSheet; clicking Create fires
 * `onCreate()` so the parent can open SpriteGenerateModal in create mode.
 */
export default function SpritesBlock({ sprites, onSelect, onCreate }) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sprites;
    return sprites.filter((s) => s.slug.toLowerCase().includes(q));
  }, [sprites, query]);

  const grouped = useMemo(() => groupByPack(filtered), [filtered]);
  const packNames = useMemo(() => Object.keys(grouped).sort(), [grouped]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[160px]">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-whisper pointer-events-none"
          />
          <input
            type="search"
            placeholder="Search by slug…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-2 rounded border border-ink-page-shadow bg-ink-page text-ink-primary text-sm"
            aria-label="Search sprites by slug"
          />
        </div>
        <Button variant="primary" size="sm" onClick={onCreate}>
          <Plus size={14} aria-hidden className="mr-1" />
          Create sprite
        </Button>
      </div>

      {sprites.length === 0 ? (
        <EmptyState>
          No sprites registered yet. Click "Create sprite" to author the first one.
        </EmptyState>
      ) : filtered.length === 0 ? (
        <EmptyState>No sprites match "{query}".</EmptyState>
      ) : (
        <div className="space-y-5">
          {packNames.map((pack) => (
            <SpritePack key={pack} pack={pack} rows={grouped[pack]} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

function SpritePack({ pack, rows, onSelect }) {
  return (
    <details open={pack !== 'default'}>
      <summary className="cursor-pointer mb-2 flex items-center gap-2">
        <h4 className="font-display text-sm font-semibold text-ink-secondary uppercase tracking-wide">
          {pack}
        </h4>
        <span className="text-tiny text-ink-whisper">({rows.length})</span>
      </summary>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
        {rows.map((s) => (
          <button
            key={s.slug}
            type="button"
            onClick={() => onSelect(s)}
            className="rounded-xl p-3 text-center border border-ink-page-shadow bg-ink-page-aged/50 cursor-pointer transition-transform hover:-translate-y-0.5"
          >
            <div className="flex items-center justify-center h-12 mb-1">
              <RpgSprite spriteKey={s.slug} size={40} alt={s.slug} />
            </div>
            <div className="text-xs font-mono leading-tight text-ink-primary line-clamp-1" title={s.slug}>
              {s.slug}
            </div>
            <div className="text-micro mt-1 text-ink-whisper">
              {s.frame_count > 1 ? `${s.frame_count}f · ${s.fps}fps` : 'static'}
            </div>
          </button>
        ))}
      </div>
    </details>
  );
}
