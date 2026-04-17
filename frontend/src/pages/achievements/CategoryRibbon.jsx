import { useCallback, useEffect, useRef } from 'react';
import CategoryPennant from './CategoryPennant';

/**
 * CategoryRibbon — wrapped tablist of CategoryPennant tabs.
 *
 * Previously a horizontal snap-scroll ribbon; on narrow viewports that
 * buried any category past the fourth with no discovery affordance, so
 * the pennants now wrap onto multiple rows. Every category is always
 * visible. `role="tablist"` + `role="tab"` semantics preserved; arrow
 * keys continue to move selection linearly with wrap-around, and the
 * `scrollIntoView` effect still kicks in when a selected pennant sits
 * in a wrapped row outside the scroll viewport (long category lists).
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
      className="flex flex-wrap gap-2 pb-1"
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
