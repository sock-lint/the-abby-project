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
    <div className="relative pt-3 pb-2">
      {/* Wooden shelf board — a sepia plank under the tomes with a
          repeating-linear-gradient grain pattern. The plank takes ~14 px
          of the bottom edge and the spines sit on top of it (z-0 board,
          spines render above via stacking). A soft outer shadow lets the
          plank cast under the row. */}
      <div
        aria-hidden="true"
        data-shelf-board="true"
        className="shelf-board absolute inset-x-0 bottom-0 h-3 rounded-sm"
      />
      {/* Plank front-lip shadow — a slightly darker sliver right under the
          board, gives the shelf its sense of "in front of the wall." */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 -bottom-1 h-1 bg-gradient-to-b from-[rgba(45,31,21,0.30)] to-transparent rounded-b-sm pointer-events-none"
      />
      <div
        role="tablist"
        aria-orientation="horizontal"
        aria-label={ariaLabel}
        className="relative flex gap-2 md:gap-3 overflow-x-auto pt-4 pb-4 px-1 snap-x snap-mandatory"
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
            variant={item.variant}
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
