import { useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { SuccessToastContext } from '../contexts/SuccessToastContext';
import { TOAST_DURATION_SHORT } from '../constants/timing';

let nextId = 0;

function SuccessToastItem({ toast, onDismiss }) {
  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      transition={{ type: 'spring', damping: 22, stiffness: 260 }}
      onAnimationComplete={(def) => {
        if (def === 'animate') {
          setTimeout(() => onDismiss(toast.id), TOAST_DURATION_SHORT);
        }
      }}
      className="flex items-center gap-2 rounded-lg border border-moss bg-gradient-to-r from-moss/90 to-moss/80 px-3 py-2 shadow-lg pointer-events-auto"
    >
      <CheckCircle2 size={18} className="text-white shrink-0" aria-hidden="true" />
      <span className="text-caption font-semibold text-white truncate">{toast.message}</span>
    </motion.div>
  );
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
