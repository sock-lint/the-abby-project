import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sword, X } from 'lucide-react';

import { useQuestProgressToasts } from '../hooks/useQuestProgressToasts';
import IconButton from './IconButton';

const AUTO_DISMISS_MS = 4000;

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      className="flex items-center gap-3 rounded-lg border border-royal/60 bg-gradient-to-r from-royal to-royal/80 px-3 py-2 shadow-lg"
    >
      <Sword size={18} className="text-white shrink-0" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-white">
          +{toast.delta} toward {toast.name}
        </div>
        <div className="text-micro text-white/85">
          {toast.percent}% complete
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
 * QuestProgressToastStack — child-only floater that surfaces active-quest
 * progress increments. Polls /api/quests/active/ via the hook and emits
 * a 4s toast whenever current_progress climbs.
 *
 * Sibling of DropToastStack / SavingsToastStack / ApprovalToastStack;
 * stacked beneath them so the more emotional events (drops, approvals)
 * don't get hidden under a quest-progress floater.
 */
export default function QuestProgressToastStack() {
  const { toasts, dismiss } = useQuestProgressToasts();
  return (
    <div className="fixed top-52 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
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
