import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ModalBackdrop from './modal/ModalBackdrop';
import SealCloseButton from './modal/SealCloseButton';
import SealPulseRing from './modal/SealPulseRing';

// Tiny local hook — avoids shipping a new shared utility just for one modal.
function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined') return true;
    return window.matchMedia('(min-width: 768px)').matches;
  });
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = (e) => setIsDesktop(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isDesktop;
}

// Long-form modal shell. Dual-mode under the "Sheikah Stamp" DNA:
//   Desktop (md+)   — centered parchment card with stamp-in motion,
//                     matches FormModal's feel but wider (max-w-lg).
//   Mobile          — retains the bottom-sheet slide (thumb-reach),
//                     adds a sheikah-glyph drag handle, a one-shot teal
//                     halo across the top edge, deckle-style divider,
//                     and the parchment texture carries through.
export default function BottomSheet({ title, onClose, disabled, children }) {
  const isDesktop = useIsDesktop();

  return createPortal(
    <AnimatePresence>
      <ModalBackdrop onClick={onClose} disabled={disabled} zIndex="z-40" />
      {isDesktop ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
          <motion.div
            key="sheet-desktop"
            initial={{ scale: 0.88, opacity: 0, rotate: -1.5 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            exit={{ scale: 0.94, opacity: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 260 }}
            className="pointer-events-auto relative w-full max-w-lg parchment-bg-aged border border-ink-page-shadow rounded-2xl modal-seal-ring max-h-[85vh] overflow-y-auto overflow-x-hidden scrollbar-hide"
          >
            <SealPulseRing rounded="rounded-2xl" />
            <div className="relative flex items-center justify-between px-5 pt-4 pb-2">
              <h2 className="font-display text-lg font-bold text-ink-primary">{title}</h2>
              <SealCloseButton onClick={onClose} disabled={disabled} />
            </div>
            <div className="relative px-5 pb-5 space-y-3">
              {children}
            </div>
          </motion.div>
        </div>
      ) : (
        <motion.div
          key="sheet-mobile"
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          className="fixed bottom-0 left-0 right-0 parchment-bg-aged border-t border-ink-page-shadow rounded-t-2xl z-50 pb-[env(safe-area-inset-bottom)] max-h-[90vh] overflow-y-auto overflow-x-hidden scrollbar-hide modal-seal-ring"
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
          {/* Sheikah-glyph drag handle — replaces the anonymous grey pill. */}
          <div className="flex justify-center pt-2">
            <div
              className="w-12 h-1.5 rounded-full animate-rune-pulse"
              style={{
                background:
                  'linear-gradient(to right, transparent, var(--color-sheikah-teal) 50%, transparent)',
              }}
            />
          </div>
          <div className="flex items-center justify-between px-4 pt-3 pb-2">
            <h2 className="font-display text-lg font-bold text-ink-primary">{title}</h2>
            <SealCloseButton onClick={onClose} disabled={disabled} />
          </div>
          <div className="px-4 pb-4 space-y-3">
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
