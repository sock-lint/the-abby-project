import { useEffect, useRef } from 'react';
import { useReducedMotion } from 'framer-motion';
import useScrollFades from '../../hooks/useScrollFades';

/**
 * TabList — shared role="tablist" strip used by ChapterHub, Manage, and
 * ProjectDetail. Each call site used to re-implement the same pattern (raw
 * <button role="tab"> with hand-rolled active/inactive class strings), so
 * styling fixes had to land in three places. Both retained variants now use
 * soft rounded pills. Pass `stretch` to give each tab `flex-1` instead of
 * `shrink-0`; overflowing strips can show a small mobile position indicator.
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
  const tabRefs = useRef(new Map());
  const reducedMotion = useReducedMotion();
  const { showLeft, showRight, onScroll } = useScrollFades(stripRef);
  const fadesActive = scrollFades && (showLeft || showRight);

  // Keep the active tab visible when the strip overflows (7 Quests tabs on a
  // 390px phone). Deep links and the remembered-tab restore can land on a
  // right-side tab with the strip pinned far left — same fix TomeShelf ships.
  useEffect(() => {
    if (activeId == null) return;
    const node = tabRefs.current.get(activeId);
    const strip = stripRef.current;
    if (node && strip) {
      const tab = node.getBoundingClientRect();
      const rail = strip.getBoundingClientRect();
      strip.scrollTo?.({
        left: Math.max(0, strip.scrollLeft + tab.left - rail.left - (strip.clientWidth - tab.width) / 2),
        behavior: reducedMotion ? 'auto' : 'smooth',
      });
    }
  }, [activeId, reducedMotion]);

  const focusId = tabs.some((tab) => tab.id === activeId) ? activeId : tabs[0]?.id;
  const handleKeyDown = (event, id) => {
    const index = tabs.findIndex((tab) => tab.id === id);
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    const nextId = tabs[next].id;
    tabRefs.current.get(nextId)?.focus({ preventScroll: true });
    onSelect(nextId);
  };

  const setTabRef = (id) => (node) => {
    if (node) tabRefs.current.set(id, node);
    else tabRefs.current.delete(id);
  };

  const isBookmark = variant === 'bookmark';
  const sizing = stretch ? 'flex-1' : 'shrink-0';
  const wrapClass = isBookmark
    ? 'flex flex-nowrap gap-1.5 bg-ink-page-aged/70 rounded-2xl p-1.5 border border-ink-page-shadow/50 overflow-x-auto scrollbar-hide'
    : 'flex flex-nowrap gap-1 bg-ink-page-aged/70 rounded-2xl p-1.5 border border-ink-page-shadow/50 overflow-x-auto scrollbar-hide';

  const fadeFrom = 'from-ink-page-aged';
  const fadeTo = 'from-ink-page-aged';

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
        aria-orientation="horizontal"
        onScroll={onScroll}
        className={wrapClass}
      >
        {tabs.map((tab) => {
          const active = tab.id === activeId;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              ref={setTabRef(tab.id)}
              role="tab"
              type="button"
              aria-selected={active}
              tabIndex={tab.id === focusId ? 0 : -1}
              onKeyDown={(event) => handleKeyDown(event, tab.id)}
              onClick={() => onSelect(tab.id)}
              className={`${sizing} min-h-11 py-2 px-4 rounded-full border font-body font-semibold text-body whitespace-nowrap transition-colors flex items-center justify-center gap-2
                ${active
                  ? 'bg-sheikah-teal/15 border-sheikah-teal/20 text-ink-primary'
                  : 'border-transparent text-ink-secondary hover:text-ink-primary hover:bg-ink-page'
                }`}
            >
              {Icon && <Icon size={16} className={active ? 'text-sheikah-teal-deep' : ''} />}
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
