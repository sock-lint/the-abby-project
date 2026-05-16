import RuneBadge from './journal/RuneBadge';
import { chapterMark } from './atlas/mastery.constants';

/**
 * SectionHeader — non-collapsible sibling of AccordionSection. Use when a
 * section should always be open but still wants the same journal vocabulary
 * (script kicker, atlas chapter numeral, display title, optional count badge,
 * optional right-aligned actions slot).
 *
 * Props:
 *   title    : display title (required)
 *   index    : optional 0-based section index — renders an atlas chapter
 *              numeral (§I, §II, …) inline with the title
 *   kicker   : caveat-script line above the title
 *   count    : optional numeric badge beside the title (RuneBadge tone="teal")
 *   actions  : ReactNode rendered right-aligned (buttons, links, filters)
 *   children : optional supporting body line under the title row
 *   as       : heading element to render (default 'h2'); use 'h3' for nested
 */
export default function SectionHeader({
  title,
  index,
  kicker,
  count,
  actions,
  children,
  as: Tag = 'h2',
  className = '',
}) {
  return (
    <header className={`flex items-start gap-3 ${className}`}>
      <div className="flex-1 min-w-0">
        {kicker && (
          <div className="font-script text-sheikah-teal-deep text-caption">
            {kicker}
          </div>
        )}
        <div className="flex items-baseline gap-2 flex-wrap">
          {index != null && (
            <span
              aria-hidden="true"
              className="font-display italic text-ember-deep text-body md:text-lede leading-none select-none shrink-0"
            >
              {chapterMark(index)}
            </span>
          )}
          <Tag className="font-display text-lede md:text-xl text-ink-primary leading-tight">
            {title}
          </Tag>
          {count != null && (
            <RuneBadge tone="teal" size="sm">{count}</RuneBadge>
          )}
        </div>
        {children && (
          <div className="mt-1 font-body text-caption text-ink-secondary">
            {children}
          </div>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 shrink-0">{actions}</div>
      )}
    </header>
  );
}
