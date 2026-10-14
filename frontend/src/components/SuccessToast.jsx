import { useCallback, useEffect, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { SuccessToastContext } from '../contexts/SuccessToastContext';
import NotificationToast from './NotificationToast';
import { TOAST_DURATION_SHORT } from '../constants/timing';

let nextId = 0;

function SuccessToastItem({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_SHORT);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);
  return <NotificationToast
    tone="success" icon={<CheckCircle2 size={18} />}
    title={toast.message} onDismiss={() => onDismiss(toast.id)}
    className="pointer-events-auto"
  />;
}

function SuccessToastStack({ toasts, onDismiss }) {
  if (toasts.length === 0) return null;
  return (
    // Same anchor as JournalShell's shared toast band: stacked ABOVE the FAB
    // on phones, top-right at lg. The provider mounts above the shell in
    // App.jsx so it can't render into that band inline, so the two anchors
    // have to be kept in step — 9.5rem clears the whole FAB zone including
    // the clocked-in timer pill, which a 5.5rem/right-20 reserve does not.
    <div
      className="fixed z-50 space-y-2 pointer-events-none
                 bottom-[calc(env(safe-area-inset-bottom)+9.5rem)] left-4 right-4
                 lg:bottom-auto lg:left-auto lg:right-4 lg:top-[calc(env(safe-area-inset-top)+1rem)]
                 lg:w-80 lg:max-w-[calc(100vw-2rem)]"
      aria-live="polite"
      aria-atomic="false"
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((t) => (
          <SuccessToastItem key={t.id} toast={t} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}

export default function SuccessToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showSuccess = useCallback((message) => {
    const id = ++nextId;
    setToasts((prev) => [...prev.slice(-3), { id, message }]);
    return id;
  }, []);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <SuccessToastContext.Provider value={showSuccess}>
      {children}
      <SuccessToastStack toasts={toasts} onDismiss={dismiss} />
    </SuccessToastContext.Provider>
  );
}
