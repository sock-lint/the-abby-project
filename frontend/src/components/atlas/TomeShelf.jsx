import { useRef } from 'react';
import TomeSpine from './TomeSpine';

/**
 * Wrapping collection navigation. The legacy name and flat item descriptors
 * stay compatible: { id, name, icon, chip?, progressPct?, tier?, ariaLabel? }.
 * Collection categories use cards; an all-vessel set uses compact filter pills.
 * Both layouts expose a single tablist with one tab stop at every viewport size.
 */
export default function TomeShelf({ items, activeId, onSelect, ariaLabel }) {
  const refs = useRef(new Map());
  const focusId = items.some((item) => item.id === activeId) ? activeId : items[0]?.id;

  const handleKeyDown = (event, id) => {
    const index = items.findIndex((item) => item.id === id);
    let nextIndex;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % items.length;
    else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + items.length) % items.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = items.length - 1;
    else return;

    event.preventDefault();
    const nextId = items[nextIndex].id;
    // Intentional keyboard navigation reveals the target between the shell's
    // sticky header and fixed bottom bar. Mount/external selection stays inert.
    const node = refs.current.get(nextId);
    node?.focus({ preventScroll: true });
    const bounds = node?.getBoundingClientRect();
    if (bounds) {
      const header = document.querySelector('[data-journal-sticky-header="true"]')?.getBoundingClientRect();
      const bottomNav = document.querySelector('[data-journal-bottom-nav="true"]')?.getBoundingClientRect();
      const visibleTop = header?.height > 0 && header.bottom > 0 && header.top < window.innerHeight
        ? Math.max(0, Math.min(window.innerHeight, header.bottom)) : 0;
      const visibleBottom = bottomNav?.height > 0 && bottomNav.top < window.innerHeight && bottomNav.bottom > 0
        ? Math.max(0, Math.min(window.innerHeight, bottomNav.top)) : window.innerHeight;

      // Include shell occlusion and the focus ring in nearest scrolling.
      node.style.scrollMarginTop = `${visibleTop + 4}px`;
      node.style.scrollMarginBottom = `${window.innerHeight - visibleBottom + 4}px`;
      if (
        bounds.top < visibleTop || bounds.bottom > visibleBottom ||
        bounds.left < 0 || bounds.right > window.innerWidth
      ) {
        node.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
      }
    }
    onSelect(nextId);
  };

  if (!items.length) return null;

  const allVessel = items.every((item) => item.variant === 'vessel');

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      aria-label={ariaLabel}
      data-collection-layout={allVessel ? 'pills' : 'cards'}
      className={allVessel ? 'flex flex-wrap gap-2' : 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3'}
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
          compact={allVessel}
          active={activeId === item.id}
          tabIndex={item.id === focusId ? 0 : -1}
          ariaLabel={item.ariaLabel}
          onClick={() => onSelect(item.id)}
          onKeyDown={(event) => handleKeyDown(event, item.id)}
        />
      ))}
    </div>
  );
}
