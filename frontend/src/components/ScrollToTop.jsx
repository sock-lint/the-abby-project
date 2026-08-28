import { useLayoutEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * ScrollToTop — resets window scroll on every pathname change. SPA pushState
 * navigation keeps the previous page's scroll position, so without this a
 * non-hub page (Dashboard, ProjectDetail, Settings…) opens mid-scroll after
 * the user was deep in another chapter.
 *
 * Keyed on pathname ONLY: `?tab=` switches inside a hub are ChapterHub's job
 * (it owns a smooth intra-hub scroll reset) and must not double-fire here.
 * The reset is instant, not smooth, so it doesn't animate against the
 * PageTurnTransition cross-fade.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname]);

  return null;
}
