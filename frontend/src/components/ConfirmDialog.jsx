import { useId } from 'react';
import { createPortal } from 'react-dom';
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
  const titleId = useId();
  const messageId = useId();
  return createPortal(
    <AnimatePresence>
      {/* Backdrop is a sibling of the centering wrapper (not a child) so the
          z-40 ink-wash can't paint over the z-auto card — otherwise clicks on
          Confirm land on the backdrop's onCancel instead. Mirrors BottomSheet. */}
      <ModalBackdrop onClick={onCancel} zIndex="z-40" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        {/* Wrapper holds the pulse ring. The inner card carries the deckle mask
            (which would otherwise clip the ring). */}
        <motion.div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={messageId}
          className="pointer-events-auto relative max-w-sm w-full"
          initial={{ scale: 0.82, opacity: 0, rotate: -3 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: 'spring', damping: 20, stiffness: 240 }}
        >
          <SealPulseRing rounded="rounded-[22px]" />
          <div className="relative parchment-bg-aged deckle-edge p-6 modal-seal-ring-strong">
            <h3 id={titleId} className="font-display font-bold text-lg text-ink-primary mb-2">
              {title}
            </h3>
            <p id={messageId} className="text-sm text-ink-secondary mb-5 leading-relaxed">
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
                    'radial-gradient(circle at 30% 30%, #e88a5e 0%, #d97548 55%, #a04a28 100%)', // intentional: theme-invariant ember seal palette — must NOT bind to --color-ember (varies per cover)
                  // ink-tone stops route through --color-modal-* tokens so Vigil and other covers can override;
                  // the colored 0 3px 8px ember-tinted shadow stays literal — same theme-invariant wax-seal palette
                  // as the gradient stops above.
                  boxShadow:
                    'inset 0 1px 2px rgba(255, 248, 224, 0.45), inset 0 -2px 4px var(--color-modal-shadow), 0 3px 8px rgba(160, 74, 40, 0.5)',
                  textShadow: '0 1px 1px var(--color-modal-shadow-strong)',
                }}
              >
                {confirmLabel}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>,
    document.body,
  );
}
