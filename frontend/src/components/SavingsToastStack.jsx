import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Trophy } from 'lucide-react';
import { useSavingsCompletionToasts } from '../hooks/useSavingsCompletionToasts';
import NotificationToast from './NotificationToast';
import { TOAST_DURATION_LONG } from '../constants/timing';

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_LONG);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  // Gold-leaf tier surface — the journal's "treasure" hue, matching the drop
  // toasts this shares a band with rather than a raw Tailwind amber gradient.
  return (
    <NotificationToast
      rarity="legendary"
      onDismiss={() => onDismiss(toast.id)}
    >
      <Trophy size={18} className="text-current shrink-0" />
      <span className="text-xl shrink-0" aria-hidden="true">{toast.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-caption font-semibold text-current">
          Savings goal reached!
        </div>
        <div className="text-caption text-current truncate">
          {toast.title} · +{toast.coin_bonus} coins
        </div>
      </div>
    </NotificationToast>
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
