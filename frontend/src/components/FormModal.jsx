import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

// Shared modal shell used by Chores, Rewards, Habits, Payments, and
// Achievements for form-style dialogs. Slides up from the bottom on mobile,
// centers on desktop. Wrap content in a <form> if needed.
//
// Props:
//   title    - header text
//   onClose  - close handler (invoked by backdrop click and the X button)
//   size     - "md" (max-w-md) or "lg" (max-w-lg, default)
//   scroll   - when true (default) caps height at 85vh and scrolls; set false
//              for short fixed-height modals (e.g. confirmation dialogs)
export default function FormModal({
  title, onClose, size = 'lg', scroll = true, children,
}) {
  const widthClass = size === 'md' ? 'md:max-w-md' : 'md:max-w-lg';
  const scrollClass = scroll ? 'max-h-[85vh] overflow-y-auto' : '';
  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      >
        <div className="absolute inset-0 bg-black/60" onClick={onClose} />
        <motion.div
          className={`relative w-full ${widthClass} bg-ink-page-aged border border-ink-page-shadow rounded-t-2xl md:rounded-2xl p-5 ${scrollClass}`}
          initial={{ y: '100%' }} animate={{ y: 0 }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-lg font-bold">{title}</h3>
            <button
              type="button"
              onClick={onClose}
              className="text-ink-whisper hover:text-ink-primary"
              aria-label="Close"
            >
              <X size={20} />
            </button>
          </div>
          {children}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
