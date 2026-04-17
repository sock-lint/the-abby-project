import { useCallback, useEffect, useRef } from 'react';
import CategoryPennant from './CategoryPennant';

/**
 * CategoryRibbon — horizontal snap-scroll of CategoryPennant tabs.
 *
 * Maintains role="tablist" / role="tab" semantics and keeps the selected
 * pennant scrolled into view as the caller flips `activeId`. Arrow keys
 * move selection (wrap around). The container is edge-faded via a mask
 * so long category names hint at being scrollable.
 */
export default function CategoryRibbon({
  categories,
  activeId,
  onSelect,
  summaryByCategory,
}) {
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

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      aria-label="Skill categories"
      className="flex gap-2 overflow-x-auto pb-2 snap-x snap-mandatory scrollbar-hide"
      style={{
        maskImage:
          'linear-gradient(to right, transparent, black 20px, black calc(100% - 20px), transparent)',
        WebkitMaskImage:
          'linear-gradient(to right, transparent, black 20px, black calc(100% - 20px), transparent)',
      }}
    >
      {categories.map((cat) => (
        <CategoryPennant
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
  );
}
