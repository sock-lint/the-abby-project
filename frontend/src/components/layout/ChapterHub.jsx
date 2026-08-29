import { useEffect, useState } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import { motion, useDragControls } from 'framer-motion';
import DeckleDivider from '../journal/DeckleDivider';
import TabList from './TabList';
import { inkBleed } from '../../motion/variants';
import { STORAGE_KEYS } from '../../constants/storage';

// Horizontal travel before a swipe counts as a tab change.
const SWIPE_TAB_THRESHOLD_PX = 70;

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

  // Tab bodies stay mounted once visited and are hidden rather than torn down.
  // Keying the body on activeTab.id remounted the whole page on every tap or
  // swipe: `useApi` has no cache, so each flip re-ran every fetch behind a
  // full-tab loader and dropped in-tab state (search text, filter pills,
  // expanded folios). Retained bodies live only as long as the hub itself —
  // leaving the chapter unmounts them all.
  const [visitedIds, setVisitedIds] = useState(() => [activeTab.id]);

  const setTab = (id) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', id);
    setSearchParams(next, { replace: true });
    localStorage.setItem(storageKey, id);
    // Remember both sides of the flip: the body being left stays mounted, and
    // the one being entered is retained for the trip back.
    setVisitedIds((prev) => {
      const withCurrent = prev.includes(activeTab.id) ? prev : [...prev, activeTab.id];
      return withCurrent.includes(id) ? withCurrent : [...withCurrent, id];
    });
  };

  const mountedTabs = tabs.filter(
    (t) => t.id === activeTab.id || visitedIds.includes(t.id),
  );

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [activeTab.id]);

  // Swipe between tabs. The mobile dot row under the strip already reads as a
  // pager, and the strip is not sticky — without this, switching tabs from
  // deep in a list means scrolling back to the top first.
  const dragControls = useDragControls();
  const activeIndex = tabs.findIndex((t) => t.id === activeTab.id);

  const startSwipe = (event) => {
    // Desktop keeps click-to-switch; hijacking mouse drags would break text
    // selection for no gain (the whole strip is visible at md+ anyway).
    if (event.pointerType === 'mouse') return;
    // Yield to any horizontally-scrollable ancestor under the finger — tab
    // strips, TomeShelf rails and vessel pill rows own their own pans.
    let node = event.target;
    while (node && node !== event.currentTarget) {
      if (node.scrollWidth > node.clientWidth + 1
        && /(auto|scroll)/.test(getComputedStyle(node).overflowX)) return;
      node = node.parentElement;
    }
    dragControls.start(event);
  };

  const handleSwipeEnd = (_event, info) => {
    if (Math.abs(info.offset.x) < SWIPE_TAB_THRESHOLD_PX) return;
    const step = info.offset.x < 0 ? 1 : -1;
    const next = tabs[activeIndex + step];
    if (next) setTab(next.id);
  };

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
        drag="x"
        dragControls={dragControls}
        dragListener={false}
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={0.15}
        onPointerDown={startSwipe}
        onDragEnd={handleSwipeEnd}
      >
        {mountedTabs.map((t) => (
          <motion.div
            key={t.id}
            hidden={t.id !== activeTab.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            {t.render()}
          </motion.div>
        ))}
      </motion.div>
    </motion.div>
  );
}
