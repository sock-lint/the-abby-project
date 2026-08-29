import { useCallback, useEffect, useRef } from 'react';
import TomeSpine from './TomeSpine';
import useScrollFades from '../../hooks/useScrollFades';

/**
 * TomeShelf — horizontal snap-scroll rail of TomeSpine tabs.
 *
 * Contract: role="tablist", role="tab" per child, arrow-key nav with
 * wrap-around, scrollIntoView fires when activeId changes so the chosen
 * spine is centered even in a long catalog. The shelf itself is styled
 * with a warm underglow + bottom hairline suggesting a wooden display
 * shelf. Domain-agnostic — each `item` is a flat spine descriptor:
 * `{ id, name, icon, chip?, progressPct?, tier?, ariaLabel? }`.
 *
 * Phone-aware vessels: when EVERY item is `variant: 'vessel'` (a small
 * filter set — Companions/Mounts buckets, QuestCodex kinds, satchel
 * compartments), the tall spine rail costs ~230px of phone height for what
 * is really a 2-4 way picker. Below md those shelves render instead as a
 * horizontal pill row (icon + label + count chip, TabList's pill visual
 * language) and the spine rail is CSS-hidden (`hidden md:block`), so
 * existing markup — role="tablist"/"tab", data-spine-* — stays in the DOM
 * for tests and for md+ viewports. The pills are plain buttons wired to
 * the same `onSelect` with `aria-pressed` state — NOT role="tab" — so a
 * page never exposes two tablists for one picker. Codex/category shelves
 * keep the full spine rail at every width.
 */
export default function TomeShelf({ items, activeId, onSelect, ariaLabel }) {
  const refs = useRef(new Map());
  const shelfRef = useRef(null);
  const { showLeft, showRight, onScroll: onShelfScroll } = useScrollFades(shelfRef);

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

  const allVessel = items.every((item) => item.variant === 'vessel');

  return (
    <>
      {allVessel && (
        <div
          role="group"
          aria-label={ariaLabel}
          data-vessel-pills="true"
          className="md:hidden flex flex-nowrap gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow overflow-x-auto scrollbar-hide"
        >
          {items.map((item) => {
            const active = activeId === item.id;
            return (
              <button
                key={item.id}
                type="button"
                aria-pressed={active}
                aria-label={item.ariaLabel || item.name}
                onClick={() => onSelect(item.id)}
                data-pill-id={item.id}
                className={`shrink-0 min-h-11 py-2 px-3 rounded-md font-display text-body transition-colors flex items-center gap-1.5 ${
                  active
                    ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                    : 'text-ink-secondary hover:text-ink-primary'
                }`}
              >
                {item.icon && (
                  <span aria-hidden="true" className="text-base leading-none">
                    {item.icon}
                  </span>
                )}
                <span>{item.name}</span>
                {item.chip != null && item.chip !== '' && (
                  <span
                    className={`text-tiny font-rune tabular-nums px-1.5 py-0.5 rounded ${
                      active
                        ? 'bg-ink-page-rune-glow/20'
                        : 'bg-ink-page-shadow/40 text-ink-whisper'
                    }`}
                  >
                    {item.chip}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
      <div
        className={`relative pt-3 pb-2 ${allVessel ? 'hidden md:block px-2.5' : ''}`}
      >
        {allVessel ? (
          /* Cabinet case — a drawer is housed IN a frame, where a tome rests
             ON a plank. Sharing the plank was what made a row of drawers
             read as a row of books stood on a shelf. Painted behind the
             drawers (earlier in the DOM, pointer-events-none). */
          <div
            aria-hidden="true"
            data-shelf-case="true"
            className="drawer-case absolute inset-0 rounded-md pointer-events-none"
          />
        ) : (
          <>
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
          </>
        )}
        {/* Scroll-fade gradients — signal "more spines off-screen" without
            adding a scrollbar that fights the shelf-board aesthetic. Mirror
            ChapterHub's pattern so the cue reads identically across hubs and
            the Atlas shelf. */}
        {showLeft && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-0 top-0 bottom-0 w-8 z-10
                       bg-gradient-to-r from-ink-page to-transparent"
          />
        )}
        {showRight && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 z-10
                       bg-gradient-to-l from-ink-page to-transparent"
          />
        )}
        <div
          ref={shelfRef}
          role="tablist"
          aria-orientation="horizontal"
          aria-label={ariaLabel}
          onScroll={onShelfScroll}
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
    </>
  );
}
