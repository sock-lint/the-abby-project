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
      <span className="text-xs font-semibold text-white truncate">{toast.message}</span>
    </motion.div>
  );
}

function SuccessToastStack({ toasts, onDismiss }) {
  if (toasts.length === 0) return null;
  return (
    <div
      className="fixed bottom-28 right-4 lg:bottom-8 lg:right-6 z-50 space-y-2 w-72 max-w-[calc(100vw-2rem)] pointer-events-none"
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
