import { useCallback, useEffect, useRef } from 'react';
import TomeSpine from './TomeSpine';

/**
 * TomeShelf — horizontal snap-scroll rail of TomeSpine tabs.
 *
 * Contract: role="tablist", role="tab" per child, arrow-key nav with
 * wrap-around, scrollIntoView fires when activeId changes so the chosen
 * spine is centered even in a long catalog (the 14-category skill tree
 * needs horizontal paging, not wrap). The shelf itself is styled with a
 * warm underglow + top hairline suggesting a wooden display shelf.
 */
export default function TomeShelf({ categories, activeId, onSelect, summaryByCategory }) {
  const refs = useRef(new Map());

  const handleKey = useCallback(
    (event) => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      if (!categories.length) return;
      event.preventDefault();
      const idx = categories.findIndex((c) => c.id === activeId);
      const step = event.key === 'ArrowRight' ? 1 : -1;
      const nextIdx = ((idx === -1 ? 0 : idx) + step + categories.length) % categories.length;
      onSelect(categories[nextIdx].id);
    },
    [activeId, categories, onSelect],
  );

  useEffect(() => {
    if (activeId == null) return;
    const node = refs.current.get(activeId);
    if (node?.scrollIntoView) {
      node.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      node.focus?.({ preventScroll: true });
    }
  }, [activeId]);

  if (!categories.length) return null;

  return (
    <div className="relative">
      {/* Shelf ledge — a thin sepia gradient under the tomes reads as a
          wooden shelf lip without needing a raster asset. */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-2 bg-gradient-to-b from-ember-deep/10 via-ink-page-shadow/40 to-ink-page-shadow/70 rounded"
      />
      <div
        role="tablist"
        aria-orientation="horizontal"
        aria-label="Skill categories"
        className="relative flex gap-2 md:gap-3 overflow-x-auto pt-2 pb-3 px-1 snap-x snap-mandatory"
        style={{ scrollbarWidth: 'thin' }}
      >
        {categories.map((cat) => (
          <TomeSpine
            key={cat.id}
            ref={(node) => {
              if (node) refs.current.set(cat.id, node);
              else refs.current.delete(cat.id);
            }}
            category={cat}
            active={activeId === cat.id}
            summary={summaryByCategory?.[cat.id]}
            onClick={() => onSelect(cat.id)}
            onKeyDown={handleKey}
          />
        ))}
      </div>
    </div>
  );
}
