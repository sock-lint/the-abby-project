import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Trophy } from 'lucide-react';
import { useSavingsCompletionToasts } from '../hooks/useSavingsCompletionToasts';
import IconButton from './IconButton';
import { TOAST_DURATION_LONG } from '../constants/timing';
import { swipeToDismiss } from './toastSwipe';
import { RARITY_SOLID_COLORS } from '../constants/colors';

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_LONG);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  // Gold-leaf tier surface — the journal's "treasure" hue, matching the drop
  // toasts this shares a band with rather than a raw Tailwind amber gradient.
  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      {...swipeToDismiss(() => onDismiss(toast.id))}
      className={`flex items-center gap-3 rounded-lg border border-white/25 px-3 py-2 shadow-lg ${RARITY_SOLID_COLORS.legendary}`}
    >
      <Trophy size={18} className="text-white shrink-0" />
      <span className="text-xl shrink-0" aria-hidden="true">{toast.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-caption font-semibold text-white">
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
export default function SavingsToastStack({ inline = false }) {
  const { toasts, dismiss } = useSavingsCompletionToasts();

  const items = (
    <AnimatePresence>
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <Toast toast={t} onDismiss={dismiss} />
        </div>
      ))}
    </AnimatePresence>
  );

  if (inline) return items;
  return (
    <div className="fixed top-20 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
      {items}
    </div>
  );
}
