import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ModalBackdrop from './modal/ModalBackdrop';
import SealCloseButton from './modal/SealCloseButton';
import SealPulseRing from './modal/SealPulseRing';

// Shared modal shell used by Chores, Rewards, Habits, Payments, and
// Achievements for form-style dialogs. "Sheikah Stamp" treatment:
// warm ink wash backdrop + radial vignette, centered parchment card
// with teal glow ring and a stamp-in entry animation.
//
// Props:
//   title    - header text
//   onClose  - close handler (invoked by backdrop click and the seal button)
//   size     - "md" (max-w-md) or "lg" (max-w-lg, default)
//   scroll   - when true (default) caps height at 85vh and scrolls; set false
//              for short fixed-height modals (e.g. confirmation dialogs)
export default function FormModal({
  title, onClose, size = 'lg', scroll = true, children,
}) {
  const widthClass = size === 'md' ? 'max-w-md' : 'max-w-lg';
  const scrollClass = scroll ? 'max-h-[85vh] overflow-y-auto' : '';
  // Portal to <body> so the modal escapes any ancestor that creates a
  // containing block for fixed positioning (notably PageTurnTransition's
  // motion.div, which transforms its children and would otherwise clip
  // the backdrop to the main content area).
  return createPortal(
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <ModalBackdrop onClick={onClose} zIndex="z-40" />
        <motion.div
          className={`relative w-full ${widthClass} parchment-bg-aged border border-ink-page-shadow rounded-2xl p-5 modal-seal-ring ${scrollClass}`}
          initial={{ scale: 0.88, opacity: 0, rotate: -1.5 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          exit={{ scale: 0.94, opacity: 0, rotate: 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 260 }}
        >
          <SealPulseRing rounded="rounded-2xl" />
          <div className="relative flex items-center justify-between mb-4">
            <h3 className="font-display text-lg font-bold text-ink-primary">{title}</h3>
            <SealCloseButton onClick={onClose} />
          </div>
          <div className="relative">
            {children}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>,
    document.body,
  );
}
