import { useEffect } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import DeckleDivider from '../journal/DeckleDivider';
import TabList from './TabList';
import { inkBleed } from '../../motion/variants';
import { STORAGE_KEYS } from '../../constants/storage';

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
  const { pathname } = useLocation();
  const requestedTab = searchParams.get('tab');

  const storageKey = STORAGE_KEYS.CHAPTER_TAB_PREFIX + pathname;
  const rememberedTab = !requestedTab
    ? tabs.find((t) => t.id === localStorage.getItem(storageKey))
    : null;

  const activeTab = tabs.find((t) => t.id === requestedTab)
    || rememberedTab
    || tabs.find((t) => t.id === defaultTabId)
    || tabs[0];

  const setTab = (id) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', id);
    setSearchParams(next, { replace: true });
    localStorage.setItem(storageKey, id);
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
      {/* Chapter breadcrumb — kicker only. The active tab page owns the page
          h1; carrying a hub-level h1 here on top of the per-tab h1 stacked
          two oversized headers and ate ~80-120px above the fold on mobile.
          The `title` prop is still accepted (it falls through to `aria-label`
          on the tab strip below) so anchors and breadcrumbs are honored. */}
      {kicker && (
        <header className="text-center md:text-left mb-2">
          <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
            {kicker}
          </div>
        </header>
      )}

      {/* Tab strip — bookmark-ribbon variant of the shared TabList primitive. */}
      <TabList
        tabs={tabs}
        activeId={activeTab.id}
        onSelect={setTab}
        variant="bookmark"
        ariaLabel={`${title} sections`}
        showDots
        className="mt-3"
      />

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
