import { useLayoutEffect, useRef } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';

/**
 * ScrollToTop — resets window scroll when the user navigates FORWARD to a new
 * pathname. SPA pushState navigation keeps the previous page's scroll position,
 * so without this a non-hub page (Dashboard, ProjectDetail, Settings…) opens
 * mid-scroll after the user was deep in another chapter.
 *
 * Back navigation is exempt. Android back and the iOS edge swipe report a POP,
 * and on a phone the drill-in → back cycle is constant (open a venture from a
 * long Quests list, come back). Resetting there threw the user to the top of
 * the list every time and defeated the browser's own
 * `history.scrollRestoration`.
 *
 * Keyed on pathname ONLY: `?tab=` switches inside a hub are ChapterHub's job
 * (it owns a smooth intra-hub scroll reset) and must not double-fire here.
 * The reset is instant, not smooth, so it doesn't animate against the
 * PageTurnTransition cross-fade.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();
  const navigationType = useNavigationType();
  // null until the first render settles, so the initial mount never scrolls.
  const lastPathname = useRef(null);

  useLayoutEffect(() => {
    const changed = lastPathname.current !== null && lastPathname.current !== pathname;
    lastPathname.current = pathname;
    if (!changed) return;
    if (navigationType === 'POP') return;
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname, navigationType]);

  return null;
}
