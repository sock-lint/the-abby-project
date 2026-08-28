import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { usePwaStatus } from './PwaStatusProvider';
import { RARITY_SOLID_COLORS } from '../constants/colors';

const DISMISS_AFTER_MS = 4000;

/**
 * OfflineReadyToast — one-shot bottom-right toast confirming the service
 * worker has finished its first precache. Auto-dismisses after 4s. Modeled
 * on DropToastStack's framer-motion + setTimeout pattern.
 */
export default function OfflineReadyToast() {
  const { offlineReady, dismissOfflineReady } = usePwaStatus();

  useEffect(() => {
    if (!offlineReady) return undefined;
    const timer = setTimeout(dismissOfflineReady, DISMISS_AFTER_MS);
    return () => clearTimeout(timer);
  }, [offlineReady, dismissOfflineReady]);

  return (
    // Anchored above the fixed ChapterBottomBar on phones — at bottom-4 this
    // pointer-events-auto toast parked itself on top of the Atlas/Chronicle
    // tabs and ate taps meant for them for a full 4s, and it's the very first
    // toast a fresh install ever shows, i.e. exactly while a new kid is
    // poking at the tabs. The 9.5rem anchor is the same one JournalShell's
    // toast band uses: it clears the nav, the home-indicator inset, and the
    // FAB zone above them. Back to the corner at lg, where neither exists.
    <div
      className="fixed z-50 pointer-events-none
                 bottom-[calc(env(safe-area-inset-bottom)+9.5rem)] right-4
                 lg:bottom-4"
    >
      <AnimatePresence>
        {offlineReady && (
          <motion.div
            role="status"
            aria-live="polite"
            initial={{ x: 300, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 300, opacity: 0 }}
            // Same chip as the drop and savings toasts it shares a band with:
            // white text on a solid tier surface with a white/25 hairline.
            // The green here is the cover-invariant --color-rarity-common
            // token rather than `bg-moss`, because the dark Vigil cover
            // remaps moss to a pale #a8c48a that would strand the white text.
            className={`flex items-center gap-3 rounded-lg border border-white/25 px-3 py-2 text-caption text-white shadow-lg pointer-events-auto ${RARITY_SOLID_COLORS.common}`}
          >
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Ready to work offline.</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
