import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ModalBackdrop from './modal/ModalBackdrop';
import SealPulseRing from './modal/SealPulseRing';
import Button from './Button';
import useModalFocus from './modal/useModalFocus';

// Destructive-confirmation dialog. "Sheikah Stamp" with added drama:
// deckle-edge torn-paper card, stronger stamp rotation, ember-tinted
// ring shadow. The confirm button itself reads as a second wax seal.
//
// `stacked` — set when this dialog opens on top of another modal surface
// (BottomSheet's discard guard). See the backdrop note below.
export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Delete',
  onConfirm,
  onCancel,
  stacked = false,
}) {
  const titleId = useId();
  const messageId = useId();
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  useModalFocus({ dialogRef, initialFocusRef: cancelRef, onEscape: onCancel });
  return createPortal(
    <AnimatePresence>
      {/* Backdrop is a sibling of the centering wrapper (not a child) so the
          ink-wash can't paint over the z-auto card — otherwise clicks on
          Confirm land on the backdrop's onCancel instead. Mirrors BottomSheet.

          Standalone, z-40 sits correctly between the page and this z-50 card.
          Stacked over an open sheet it did NOT: the sheet's own surface is
          z-50, so the wash painted *behind* it and the sheet stayed both
          undimmed and fully tappable while an alertdialog claimed to be modal.
          At z-50 the wash covers the sheet and the card — later in document
          order within the same tier — still paints above the wash. No new z
          value is introduced. */}
      <ModalBackdrop onClick={onCancel} zIndex={stacked ? 'z-50' : 'z-40'} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        {/* Wrapper holds the pulse ring. The inner card carries the deckle mask
            (which would otherwise clip the ring). */}
        <motion.div
          ref={dialogRef}
          role="alertdialog"
          tabIndex={-1}
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
            <p id={messageId} className="text-body text-ink-secondary mb-5 leading-relaxed">
              {message}
            </p>
            {/* gap-4, not gap-2: this is the one row in the app where a
                slightly-off thumb aimed at the escape hatch would land on a
                destructive action. Both controls clear the 44px floor —
                Cancel via <Button>'s min-h-11, the seal explicitly. */}
            <div className="flex justify-end gap-4 items-center">
              <Button ref={cancelRef} variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
              <button
                type="button"
                onClick={onConfirm}
                className="relative min-h-11 px-5 py-2 text-body font-semibold bg-ember-deep text-ink-page-rune-glow rounded-full transition-colors hover:bg-ember-deep/90"
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
