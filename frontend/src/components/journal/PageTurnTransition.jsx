import { motion, AnimatePresence } from 'framer-motion';
import { useLocation } from 'react-router-dom';

/**
 * PageTurnTransition — wraps an <Outlet> or page content in a subtle
 * "page turning" motion when the route changes. Respects prefers-reduced-motion
 * (motion is disabled by the browser automatically via the CSS in index.css
 * and by Framer Motion's `useReducedMotion`, which we rely on implicitly).
 */
export default function PageTurnTransition({ children }) {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        // Key on pathname only. Changing search params (e.g. ?tab=…) MUST NOT
        // unmount the outlet — ChapterHub already handles its own tab fade, and
        // remounting the whole page on every tab click caused every useApi hook
        // inside to re-fire (the "duplicate API calls on navigation" bug).
        key={location.pathname}
        initial={{ opacity: 0, y: 10, rotateY: -1.5 }}
        animate={{ opacity: 1, y: 0, rotateY: 0 }}
        exit={{ opacity: 0, y: -6, rotateY: 1.5 }}
        transition={{ duration: 0.28, ease: 'easeOut' }}
        style={{ transformOrigin: 'left center' }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
