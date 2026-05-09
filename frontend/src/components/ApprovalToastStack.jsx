import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, X, XCircle } from 'lucide-react';

import { useApprovalToasts } from '../hooks/useApprovalToasts';
import IconButton from './IconButton';

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 6000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const positive = toast.positive;
  const Icon = positive ? CheckCircle2 : XCircle;
  const palette = positive
    ? 'border-moss bg-gradient-to-r from-moss/90 to-moss/80'
    : 'border-rose-300 bg-gradient-to-r from-rose-700 to-rose-600';

  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      className={`flex items-start gap-3 rounded-lg border px-3 py-2 shadow-lg ${palette}`}
    >
      <Icon size={20} className="text-white shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-white truncate">
          {toast.title}
        </div>
        {toast.message && (
          <div className="text-micro text-white/85 line-clamp-2">
            {toast.message}
          </div>
        )}
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
 * ApprovalToastStack — child-only toast strip that closes the parent
 * approval feedback loop. Polls /api/notifications/ and emits a toast
 * the first time we see each new approval-decision row (chore approved,
 * homework approved, creation approved, exchange approved, etc.).
 *
 * Sibling of DropToastStack + SavingsToastStack. Mounted globally in
 * JournalShell so the toast fires regardless of which page the child
 * is on when the parent finishes triaging.
 *
 * Stacked under the SavingsToastStack so a burst of approvals doesn't
 * overlap a savings-goal celebration.
 */
export default function ApprovalToastStack() {
  const { toasts, dismiss } = useApprovalToasts();
  return (
    <div className="fixed top-36 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
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
