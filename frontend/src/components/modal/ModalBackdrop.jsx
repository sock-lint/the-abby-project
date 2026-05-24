import { useCallback, useRef, useState } from 'react';
import { motion } from 'framer-motion';

// Shared backdrop for the "Sheikah Stamp" modal family.
// Renders two stacked layers behind a modal card:
//   1. warm ink wash + backdrop-blur (replaces the old flat bg-black/60)
//   2. radial vignette that focuses the eye toward the card
//
// Both layers fade together under <AnimatePresence> in the parent.
// The wash layer receives the click handler; the vignette is pointer-events: none.
//
// When `disabled` is true, clicking the backdrop briefly flashes the opacity
// up to signal "I heard you, but the modal can't close right now."
export default function ModalBackdrop({ onClick, disabled, zIndex = 'z-40' }) {
  const [flash, setFlash] = useState(false);
  const flashTimer = useRef(null);

  const handleClick = useCallback(() => {
    if (!disabled) {
      onClick?.();
      return;
    }
    // Brief opacity bump as visual feedback
    setFlash(true);
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(false), 150);
  }, [disabled, onClick]);

  return (
    <>
      <motion.div
        key="modal-ink-wash"
        onClick={handleClick}
        initial={{ opacity: 0 }}
        animate={{ opacity: flash ? 1.4 : 1 }}
        exit={{ opacity: 0 }}
        transition={flash ? { duration: 0.08 } : { duration: 0.25 }}
        className={`fixed inset-0 modal-ink-wash ${zIndex}`}
      />
      <motion.div
        key="modal-vignette"
        aria-hidden="true"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3, delay: 0.05 }}
        className={`fixed inset-0 modal-vignette ${zIndex}`}
      />
    </>
  );
}
