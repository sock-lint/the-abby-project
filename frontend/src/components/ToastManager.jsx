import { useCallback, useMemo, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import IconButton from './IconButton';
import NotificationToast from './NotificationToast';
import { ToastContext } from './toast.context';

let nextId = 0;

const MAX_VISIBLE = 4;

function ToastItem({ toast, onDismiss }) {
  return (
    <NotificationToast
      tone={toast.tone}
      data-notification-custom={toast.palette ? 'true' : undefined}
      className={toast.palette || ''}
    >
      {toast.icon && (
        <span className="shrink-0 mt-0.5 flex items-center">{toast.icon}</span>
      )}
      <div className="flex-1 min-w-0">
        {toast.title && (
          <div className={`text-caption font-semibold ${toast.textColor || (toast.palette ? 'text-white' : 'text-current')} truncate`}>
            {toast.title}
          </div>
        )}
        {toast.message && (
          <div className={`text-caption ${toast.subtextColor || (toast.palette ? 'text-white/85' : 'text-current')} line-clamp-2`}>
            {toast.message}
          </div>
        )}
      </div>
      <IconButton
        onClick={() => onDismiss(toast.id)}
        variant="ghost"
        size="sm"
        aria-label="Dismiss notification"
        className={`${toast.dismissColor || (toast.palette ? 'text-white/70 hover:text-white' : 'text-ink-primary hover:text-ink-primary')} shrink-0`}
      >
        <X size={14} />
      </IconButton>
    </NotificationToast>
  );
}

export default function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const push = useCallback(({ title, message, icon, palette, textColor, subtextColor, dismissColor, tone = 'neutral', duration = 6000 }) => {
    const id = `toast-${++nextId}`;
    const toast = { id, title, message, icon, palette, textColor, subtextColor, dismissColor, tone };
    setToasts((prev) => [...prev, toast]);
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
    return id;
  }, []);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const ctx = useMemo(() => ({ push, dismiss }), [push, dismiss]);

  const visible = toasts.slice(-MAX_VISIBLE);

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      <div
        className="fixed top-4 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none"
        aria-live="polite"
        aria-atomic="false"
      >
        <AnimatePresence>
          {visible.map((t) => (
            <div key={t.id} className="pointer-events-auto">
              <ToastItem toast={t} onDismiss={dismiss} />
            </div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
