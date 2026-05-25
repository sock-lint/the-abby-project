import { useRef } from 'react';
import useScrollFades from '../../hooks/useScrollFades';

/**
 * TabList — shared role="tablist" strip used by ChapterHub, Manage, and
 * ProjectDetail. Each call site used to re-implement the same pattern (raw
 * <button role="tab"> with hand-rolled active/inactive class strings), so
 * styling fixes had to land in three places. Two visual variants cover the
 * audited surfaces:
 *
 *   - `bookmark` (ChapterHub) — bookmark-ribbon tab with a teal pip above the
 *     active label and a hairline border running along the bottom of the
 *     strip. Renders an optional 6-dot mobile indicator when the strip
 *     overflows AND `tabs.length > 4`.
 *   - `pill` (Manage, ProjectDetail) — solid pill in `bg-ink-page-aged` with
 *     the active tab filled in `bg-sheikah-teal-deep`. Pass `stretch` to give
 *     each tab `flex-1` (ProjectDetail) instead of `shrink-0` (Manage).
 *
 * Scroll-fade gradients are on by default for any tab strip that can
 * overflow — pass `scrollFades={false}` to suppress (e.g. for very short
 * strips that never overflow). Mirrors `useScrollFades` (also used in
 * TomeShelf and the previous ChapterHub implementation).
 */
export default function TabList({
  tabs,
  activeId,
  onSelect,
  variant = 'bookmark',
  ariaLabel,
  stretch = false,
  scrollFades = true,
  showDots = false,
  className = '',
}) {
  const stripRef = useRef(null);
  const { showLeft, showRight, onScroll } = useScrollFades(stripRef);
  const fadesActive = scrollFades && (showLeft || showRight);

  const isBookmark = variant === 'bookmark';
  const sizing = stretch ? 'flex-1' : 'shrink-0';
  const wrapClass = isBookmark
    ? 'flex flex-nowrap gap-1.5 border-b border-ink-page-shadow pb-0 overflow-x-auto scrollbar-hide'
    : 'flex flex-nowrap gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow overflow-x-auto scrollbar-hide';

  const fadeFrom = isBookmark ? 'from-ink-page' : 'from-ink-page-aged';
  const fadeTo = isBookmark ? 'from-ink-page' : 'from-ink-page-aged';

  return (
    <div className={`relative ${className}`}>
      {scrollFades && showLeft && (
        <div
          aria-hidden="true"
          className={`pointer-events-none absolute left-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-r ${fadeFrom} to-transparent`}
        />
      )}
      {scrollFades && showRight && (
        <div
          aria-hidden="true"
          className={`pointer-events-none absolute right-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-l ${fadeTo} to-transparent`}
        />
      )}
      <nav
        ref={stripRef}
        role="tablist"
        aria-label={ariaLabel}
        onScroll={onScroll}
        className={wrapClass}
      >
        {tabs.map((tab) => {
          const active = tab.id === activeId;
          const Icon = tab.icon;
          if (isBookmark) {
            return (
              <button
                key={tab.id}
                role="tab"
                type="button"
                aria-selected={active}
                onClick={() => onSelect(tab.id)}
                className={`relative ${sizing} whitespace-nowrap px-4 py-2 font-display text-body md:text-base tracking-wide transition-colors rounded-t-lg border border-transparent -mb-px
                  ${active
                    ? 'bg-ink-page-aged text-ink-primary border-ink-page-shadow border-b-ink-page-aged'
                    : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/40'
                  }`}
              >
                {active && (
                  <span
                    className="absolute -top-1 left-1/2 -translate-x-1/2 w-6 h-1 rounded-b bg-sheikah-teal-deep"
                    aria-hidden="true"
                  />
                )}
                {tab.label}
              </button>
            );
          }
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={active}
              onClick={() => onSelect(tab.id)}
              className={`${sizing} py-2 px-3 rounded-md font-display text-body transition-colors flex items-center justify-center gap-2
                ${active
                  ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                  : 'text-ink-secondary hover:text-ink-primary'
                }`}
            >
              {Icon && <Icon size={16} />}
              {tab.label}
            </button>
          );
        })}
      </nav>
      {showDots && fadesActive && tabs.length > 4 && (
        <div className="flex justify-center mt-1.5 md:hidden" aria-hidden="true">
          <div className="flex gap-1">
            {tabs.map((tab) => (
              <span
                key={tab.id}
                className={`block w-1.5 h-1.5 rounded-full transition-colors ${
                  tab.id === activeId ? 'bg-sheikah-teal-deep' : 'bg-ink-page-shadow'
                }`}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
