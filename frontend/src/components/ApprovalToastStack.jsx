import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { CheckCircle2, XCircle } from 'lucide-react';

import { useApprovalToasts } from '../hooks/useApprovalToasts';
import NotificationToast from './NotificationToast';
import { TOAST_DURATION_LONG } from '../constants/timing';

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_LONG);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const positive = toast.positive;
  const Icon = positive ? CheckCircle2 : XCircle;

  return (
    <NotificationToast
      tone={positive ? 'success' : 'danger'}
      onDismiss={() => onDismiss(toast.id)}
    >
      <Icon size={20} className="text-current shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="text-caption font-semibold text-current truncate">
          {toast.title}
        </div>
        {toast.message && (
          <div className="text-caption text-current line-clamp-2">
            {toast.message}
          </div>
        )}
      </div>
    </NotificationToast>
  );
}

/**
 * ApprovalToastStack — personal-space toast strip for children and parents
 * in My space. Watches the shared pulse and emits a toast
 * the first time we see each new approval-decision row (chore approved,
 * homework approved, creation approved, exchange approved, etc.).
 *
 * Sibling of DropToastStack + SavingsToastStack. Mounted globally in
 * JournalShell so personal participants see decisions on any page.
 * Family keeps its review interface instead of personal decision toasts.
 *
 * Stacked under the SavingsToastStack so a burst of approvals doesn't
 * overlap a savings-goal celebration.
 */
export default function ApprovalToastStack({ inline = false }) {
  const { toasts, dismiss } = useApprovalToasts();

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
    <div className="fixed top-36 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
      {items}
    </div>
  );
}
