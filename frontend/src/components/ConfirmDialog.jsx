import { motion, AnimatePresence } from 'framer-motion';
import ModalBackdrop from './modal/ModalBackdrop';
import SealPulseRing from './modal/SealPulseRing';

// Destructive-confirmation dialog. "Sheikah Stamp" with added drama:
// deckle-edge torn-paper card, stronger stamp rotation, ember-tinted
// ring shadow. The confirm button itself reads as a second wax seal.
export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Delete',
  onConfirm,
  onCancel,
}) {
  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <ModalBackdrop onClick={onCancel} zIndex="z-40" />
        {/* Wrapper holds the pulse ring. The inner card carries the deckle mask
            (which would otherwise clip the ring). */}
        <motion.div
          className="relative max-w-sm w-full"
          initial={{ scale: 0.82, opacity: 0, rotate: -3 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: 'spring', damping: 20, stiffness: 240 }}
        >
          <SealPulseRing rounded="rounded-[22px]" />
          <div className="relative parchment-bg-aged deckle-edge p-6 modal-seal-ring-strong">
            <h3 className="font-display font-bold text-lg text-ink-primary mb-2">
              {title}
            </h3>
            <p className="text-sm text-ink-secondary mb-5 leading-relaxed">
              {message}
            </p>
            <div className="flex justify-end gap-2 items-center">
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 text-sm text-ink-whisper hover:text-ink-primary transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onConfirm}
                className="relative px-5 py-2 text-sm font-semibold text-ink-page-rune-glow rounded-full transition-transform duration-150 hover:scale-[1.03] active:scale-95"
                style={{
                  background:
                    'radial-gradient(circle at 30% 30%, #e88a5e 0%, #d97548 55%, #a04a28 100%)',
                  boxShadow:
                    'inset 0 1px 2px rgba(255, 248, 224, 0.45), inset 0 -2px 4px rgba(45, 31, 21, 0.45), 0 3px 8px rgba(160, 74, 40, 0.5)',
                  textShadow: '0 1px 1px rgba(45, 31, 21, 0.55)',
                }}
              >
                {confirmLabel}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
