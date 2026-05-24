import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import DeckleDivider from '../journal/DeckleDivider';
import useScrollFades from '../../hooks/useScrollFades';
import { inkBleed } from '../../motion/variants';

/**
 * ChapterHub — shared wrapper for the four hub pages (Quests, Bestiary,
 * Treasury, Atlas). Each hub defines its tabs array + a title/kicker; the
 * wrapper renders a chapter header, tab strip, and the active sub-tab's
 * component. Active tab is persisted in the URL via `?tab=…`.
 *
 * Props:
 *   title    : string — chapter title (displayed in Cormorant display)
 *   kicker   : string — hand-lettered label above the title
 *   glyph    : string — glyph name (see DeckleDivider's GLYPH_URLS) for the divider
 *   tabs     : Array<{ id, label, render: () => JSX }>
 *   defaultTabId? : string — tab to fall back to when ?tab= is missing
 */
export default function ChapterHub({ title, kicker, glyph = 'compass-rose', tabs, defaultTabId }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const activeTab = tabs.find((t) => t.id === requestedTab) || tabs.find((t) => t.id === defaultTabId) || tabs[0];

  const tabStripRef = useRef(null);
  const { showLeft, showRight, onScroll: onTabScroll } = useScrollFades(tabStripRef);

  const setTab = (id) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', id);
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [activeTab.id]);

  return (
    <motion.div
      variants={inkBleed}
      initial="initial"
      animate="animate"
      className="max-w-6xl mx-auto"
    >
      {/* Chapter header */}
      <header className="text-center md:text-left mb-2">
        {kicker && (
          <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
            {kicker}
          </div>
        )}
        <h1 className="font-display italic text-3xl md:text-5xl text-ink-primary leading-tight">
          {title}
        </h1>
      </header>

      {/* Tab strip — bookmark-ribbon style */}
      <div className="relative mt-3">
        {showLeft && (
          <div
            className="pointer-events-none absolute left-0 top-0 bottom-0 w-8 z-10
                       bg-gradient-to-r from-ink-page to-transparent"
            aria-hidden="true"
          />
        )}
        {showRight && (
          <div
            className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 z-10
                       bg-gradient-to-l from-ink-page to-transparent"
            aria-hidden="true"
          />
        )}
        <nav
          ref={tabStripRef}
          role="tablist"
          aria-label={`${title} sections`}
          onScroll={onTabScroll}
          className="flex flex-nowrap gap-1.5 border-b border-ink-page-shadow pb-0 overflow-x-auto scrollbar-hide"
        >
          {tabs.map((tab) => {
            const active = tab.id === activeTab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                type="button"
                aria-selected={active}
                onClick={() => setTab(tab.id)}
                className={`relative shrink-0 whitespace-nowrap px-4 py-2 font-display text-sm md:text-base tracking-wide transition-colors rounded-t-lg border border-transparent -mb-px
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
          })}
        </nav>
      </div>

      <DeckleDivider glyph={glyph} className="mt-0 mb-6" />

      <motion.div
        key={activeTab.id}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      >
        {activeTab.render()}
      </motion.div>
    </motion.div>
  );
}
