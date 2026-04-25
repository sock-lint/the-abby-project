import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { usePwaStatus } from './PwaStatusProvider';

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
    <div className="fixed bottom-4 right-4 z-50 pointer-events-none">
      <AnimatePresence>
        {offlineReady && (
          <motion.div
            role="status"
            aria-live="polite"
            initial={{ x: 300, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 300, opacity: 0 }}
            className="flex items-center gap-3 rounded-lg border border-green-400 bg-green-700 px-3 py-2 text-caption text-white shadow-lg pointer-events-auto"
          >
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Ready to work offline.</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
