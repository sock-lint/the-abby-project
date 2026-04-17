import { forwardRef } from 'react';

/**
 * CategoryPennant — a tall, tactile tab bound to one SkillCategory.
 *
 * Renders inside a CategoryRibbon's <div role="tablist">. Uses role="tab" +
 * aria-selected so screen readers announce the tablist relationship. The
 * active pennant lifts a gold-leaf underline; the inactive state keeps its
 * parchment panel inky-subtle.
 */
const CategoryPennant = forwardRef(function CategoryPennant(
  { category, active, onClick, summary, onKeyDown },
  ref,
) {
  const activeCls = active
    ? 'border-sheikah-teal-deep bg-sheikah-teal/15 text-ink-primary shadow-[0_2px_0_0_var(--color-gold-leaf)]'
    : 'border-ink-page-shadow bg-ink-page-aged text-ink-secondary hover:text-ink-primary hover:border-sheikah-teal/50';

  return (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active ? 'true' : 'false'}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      onKeyDown={onKeyDown}
      data-category-id={category.id}
      className={`snap-start shrink-0 min-w-[112px] max-w-[160px] min-h-[68px] px-3 py-2 rounded-xl border flex flex-col items-center justify-center gap-1 font-display text-sm transition-colors ${activeCls}`}
    >
      <span aria-hidden="true" className="text-2xl leading-none">
        {category.icon || '✦'}
      </span>
      <span className="text-caption leading-tight text-center line-clamp-2">
        {category.name}
      </span>
      {summary && typeof summary.level === 'number' && (
        <span className="text-micro font-rune uppercase tracking-wider text-ink-whisper">
          L{summary.level}
        </span>
      )}
    </button>
  );
});

export default CategoryPennant;
