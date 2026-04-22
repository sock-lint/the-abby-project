import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Trophy } from 'lucide-react';
import { useSavingsCompletionToasts } from '../hooks/useSavingsCompletionToasts';
import IconButton from './IconButton';

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 6000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      className="flex items-center gap-3 rounded-lg border border-amber-300 bg-gradient-to-r from-amber-600 to-amber-500 px-3 py-2 shadow-lg"
    >
      <Trophy size={18} className="text-white shrink-0" />
      <span className="text-xl shrink-0" aria-hidden="true">{toast.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-white">
          Hoard complete!
        </div>
        <div className="text-micro text-white/90 truncate">
          {toast.title} · +{toast.coin_bonus} coins
        </div>
      </div>
      <IconButton
        onClick={() => onDismiss(toast.id)}
        variant="ghost"
        size="sm"
        aria-label="Dismiss notification"
        className="text-white/70 hover:text-white shrink-0"
      >
        <X size={14} />
      </IconButton>
    </motion.div>
  );
}

/**
 * SavingsToastStack — celebrates newly-completed savings goals.
 *
 * Sibling of ``DropToastStack``; shares the same top-right z-50 region.
 * Mount once (in ``JournalShell``) so the toast fires regardless of
 * which page the child is on when they cross a hoard's target.
 */
export default function SavingsToastStack() {
  const { toasts, dismiss } = useSavingsCompletionToasts();
  return (
    <div className="fixed top-20 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
      <AnimatePresence>
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <Toast toast={t} onDismiss={dismiss} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );
}
