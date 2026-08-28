import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence, useDragControls } from 'framer-motion';
import ConfirmDialog from './ConfirmDialog';
import ModalBackdrop from './modal/ModalBackdrop';
import SealCloseButton from './modal/SealCloseButton';
import SealPulseRing from './modal/SealPulseRing';
import useIsDesktop from '../hooks/useIsDesktop';

// Shared modal shell for every form dialog in the app. Dual-mode under the
// "Sheikah Stamp" DNA:
//   Desktop (md+)   — centered parchment card with stamp-in motion (max-w-lg).
//   Mobile          — bottom-sheet slide (thumb-reach), sheikah-glyph drag
//                     handle, one-shot teal halo across the top edge,
//                     parchment texture carried through.
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])';

export default function BottomSheet({ title, onClose, disabled, dirty, footer, children }) {
  const isDesktop = useIsDesktop();
  const titleId = useId();
  const sheetHistoryId = useId();
  const dialogRef = useRef(null);
  const [confirmingClose, setConfirmingClose] = useState(false);
  // Drag-to-dismiss is scoped to the glyph handle (dragListener={false} +
  // dragControls). Binding drag="y" to the whole sheet made framer stamp
  // touch-action on the scroll container, so tall sheets couldn't scroll
  // natively on phones and a downward pan while reading dismissed the form.
  const dragControls = useDragControls();

  const safeClose = useCallback(() => {
    if (dirty && !confirmingClose) {
      setConfirmingClose(true);
      return;
    }
    setConfirmingClose(false);
    onClose();
  }, [dirty, confirmingClose, onClose]);

  const dialogCallbackRef = useCallback((node) => {
    dialogRef.current = node;
    if (node) {
      const first = node.querySelector(FOCUSABLE_SELECTOR);
      if (first) first.focus();
    }
  }, []);

  // The popstate listener below is registered once, so it needs a live
  // handle on safeClose (whose identity changes with `dirty`).
  const safeCloseRef = useRef(safeClose);
  useEffect(() => { safeCloseRef.current = safeClose; }, [safeClose]);

  // Android back (and the iOS edge-swipe) is the universal "dismiss" gesture
  // in an installed PWA with no browser chrome. Without this the back press
  // navigates the route *underneath* the sheet, unmounting the form and
  // discarding a half-typed entry without ever reaching the dirty guard.
  // A sentinel history entry makes back close the sheet instead.
  useEffect(() => {
    window.history.pushState({ abbySheet: sheetHistoryId }, '');
    const handlePop = () => {
      // Re-arm immediately: if the sheet is dirty, safeClose only opens the
      // confirm dialog and the sheet stays up — so back must stay trapped.
      window.history.pushState({ abbySheet: sheetHistoryId }, '');
      safeCloseRef.current();
    };
    window.addEventListener('popstate', handlePop);
    return () => {
      window.removeEventListener('popstate', handlePop);
      // Consume the sentinel only when it is still the current entry. If the
      // sheet closed by navigating somewhere (QuickActionsSheet rows do this),
      // popping here would undo that navigation.
      if (window.history.state?.abbySheet === sheetHistoryId) window.history.back();
    };
  }, [sheetHistoryId]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !disabled) safeClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [safeClose, disabled]);

  useEffect(() => {
    const node = dialogRef.current;
    if (!node) return;

    const handleTab = (e) => {
      if (e.key !== 'Tab') return;

      const focusable = Array.from(node.querySelectorAll(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    node.addEventListener('keydown', handleTab);
    return () => node.removeEventListener('keydown', handleTab);
  });

  return createPortal(
    <AnimatePresence>
      <ModalBackdrop onClick={safeClose} disabled={disabled} zIndex="z-40" />
      {isDesktop ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
          <motion.div
            key="sheet-desktop"
            ref={dialogCallbackRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={{ scale: 0.88, opacity: 0, rotate: -1.5 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            exit={{ scale: 0.94, opacity: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 260 }}
            className="pointer-events-auto relative w-full max-w-lg parchment-bg-aged border border-ink-page-shadow rounded-2xl modal-seal-ring max-h-[85dvh] overflow-y-auto overflow-x-hidden scrollbar-hide"
          >
            <SealPulseRing rounded="rounded-2xl" />
            <div className="relative flex items-center justify-between px-5 pt-4 pb-2">
              <h2 id={titleId} className="font-display text-lg font-bold text-ink-primary">{title}</h2>
              <SealCloseButton onClick={safeClose} disabled={disabled} />
            </div>
            <div className="relative px-5 pb-5 space-y-3">
              {children}
            </div>
            {footer && (
              <div className="sticky bottom-0 px-5 pb-5 pt-3 bg-ink-page-aged/95 border-t border-ink-page-shadow/40">
                {footer}
              </div>
            )}
          </motion.div>
        </div>
      ) : (
        <motion.div
          key="sheet-mobile"
          ref={dialogCallbackRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          drag="y"
          dragControls={dragControls}
          dragListener={false}
          dragConstraints={{ top: 0 }}
          dragElastic={0.1}
          onDragEnd={(_e, info) => {
            if (info.offset.y > 100 && !disabled) safeClose();
          }}
          className="fixed bottom-0 left-0 right-0 parchment-bg-aged border-t border-ink-page-shadow rounded-t-2xl z-50 max-h-[90dvh] flex flex-col modal-seal-ring"
        >
          {/* Top-edge teal halo — one-shot animation that radiates as the
              sheet settles, reinforcing the "paper slipped onto the journal"
              read without blocking thumb-reach. */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute left-0 right-0 -top-1 h-2 animate-halo-rise"
            style={{
              background:
                'linear-gradient(to right, transparent 0%, rgba(77, 208, 225, 0.65) 50%, transparent 100%)',
              filter: 'blur(3px)',
            }}
          />
          {/* Sheikah-glyph drag handle — the one place the dismiss gesture
              starts, so the sheet body below keeps native touch scrolling. */}
          <div
            className="flex justify-center pt-2 pb-1 -mb-1 cursor-grab active:cursor-grabbing touch-none shrink-0"
            aria-hidden="true"
            onPointerDown={(e) => dragControls.start(e)}
          >
            <div
              className="w-12 h-1.5 rounded-full animate-rune-pulse"
              style={{
                background:
                  'linear-gradient(to right, transparent, var(--color-sheikah-teal) 50%, transparent)',
              }}
            />
          </div>
          <div className="flex items-center justify-between px-4 pt-3 pb-2 shrink-0">
            <h2 id={titleId} className="font-display text-lg font-bold text-ink-primary">{title}</h2>
            <SealCloseButton onClick={safeClose} disabled={disabled} />
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden scrollbar-hide overscroll-contain pb-[env(safe-area-inset-bottom)]">
            <div className="px-4 pb-4 space-y-3" style={{ paddingBottom: footer ? '4.5rem' : undefined }}>
              {children}
            </div>
            {footer && (
              <div className="sticky bottom-0 px-4 pb-4 pt-3 bg-ink-page-aged/95 border-t border-ink-page-shadow/40 backdrop-blur-sm">
                {footer}
              </div>
            )}
          </div>
        </motion.div>
      )}
      {confirmingClose && (
        <ConfirmDialog
          title="Discard changes?"
          message="You have unsaved changes that will be lost."
          confirmLabel="Discard"
          onConfirm={() => { setConfirmingClose(false); onClose(); }}
          onCancel={() => setConfirmingClose(false)}
        />
      )}
    </AnimatePresence>,
    document.body,
  );
}
