import { useCallback, useEffect, useRef } from 'react';
import TomeSpine from './TomeSpine';

/**
 * TomeShelf — horizontal snap-scroll rail of TomeSpine tabs.
 *
 * Contract: role="tablist", role="tab" per child, arrow-key nav with
 * wrap-around, scrollIntoView fires when activeId changes so the chosen
 * spine is centered even in a long catalog. The shelf itself is styled
 * with a warm underglow + bottom hairline suggesting a wooden display
 * shelf. Domain-agnostic — each `item` is a flat spine descriptor:
 * `{ id, name, icon, chip?, progressPct?, tier?, ariaLabel? }`.
 */
export default function TomeShelf({ items, activeId, onSelect, ariaLabel }) {
  const refs = useRef(new Map());

  const handleKey = useCallback(
    (event) => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      if (!items.length) return;
      event.preventDefault();
      const idx = items.findIndex((c) => c.id === activeId);
      const step = event.key === 'ArrowRight' ? 1 : -1;
      const nextIdx = ((idx === -1 ? 0 : idx) + step + items.length) % items.length;
      onSelect(items[nextIdx].id);
    },
    [activeId, items, onSelect],
  );

  useEffect(() => {
    if (activeId == null) return;
    const node = refs.current.get(activeId);
    if (node?.scrollIntoView) {
      node.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      node.focus?.({ preventScroll: true });
    }
  }, [activeId]);

  if (!items.length) return null;

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
        aria-label={ariaLabel}
        className="relative flex gap-2 md:gap-3 overflow-x-auto pt-2 pb-3 px-1 snap-x snap-mandatory"
        style={{ scrollbarWidth: 'thin' }}
      >
        {items.map((item) => (
          <TomeSpine
            key={item.id}
            ref={(node) => {
              if (node) refs.current.set(item.id, node);
              else refs.current.delete(item.id);
            }}
            id={item.id}
            name={item.name}
            icon={item.icon}
            chip={item.chip}
            progressPct={item.progressPct}
            tier={item.tier}
            active={activeId === item.id}
            ariaLabel={item.ariaLabel}
            onClick={() => onSelect(item.id)}
            onKeyDown={handleKey}
          />
        ))}
      </div>
    </div>
  );
}
