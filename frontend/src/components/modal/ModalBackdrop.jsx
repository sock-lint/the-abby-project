import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useBodyScrollLock } from './bodyScrollLock';

// Shared backdrop for the "Sheikah Stamp" modal family.
// Renders two stacked layers behind a modal card:
//   1. warm ink wash + backdrop-blur (replaces the old flat bg-black/60)
//   2. radial vignette that focuses the eye toward the card
//
// Both layers fade together under <AnimatePresence> in the parent.
// The wash layer receives the click handler; the vignette is pointer-events: none.
//
// When `disabled` is true, clicking the backdrop briefly darkens the wash to
// signal "I heard you, but the modal can't close right now."
//
// Mounting this also locks page scroll behind the modal — see bodyScrollLock.js.

// Long enough to register as a deliberate pulse rather than a render glitch.
const FLASH_MS = 220;

export default function ModalBackdrop({ onClick, disabled, zIndex = 'z-40' }) {
  const [flash, setFlash] = useState(false);
  const flashTimer = useRef(null);

  useBodyScrollLock();

  useEffect(() => () => clearTimeout(flashTimer.current), []);

  const handleClick = useCallback(() => {
    if (!disabled) {
      onClick?.();
      return;
    }
    setFlash(true);
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(false), FLASH_MS);
  }, [disabled, onClick]);

  return (
    <>
      <motion.div
        key="modal-ink-wash"
        onClick={handleClick}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        className={`fixed inset-0 modal-ink-wash ${zIndex}`}
      />
      {/* Disabled-tap feedback. This used to animate the wash's own opacity
          from 1 to 1.4 — which CSS clamps at 1, so the "you can't close right
          now" signal was literally invisible and a mid-save tap read as a
          hang. A second translucent wash stacked on top of the first has real
          headroom to move into: it roughly doubles the dim while it's up, then
          fades back, leaving the resting appearance untouched. */}
      <motion.div
        key="modal-ink-wash-flash"
        aria-hidden="true"
        data-testid="modal-ink-wash-flash"
        initial={{ opacity: 0 }}
        animate={{ opacity: flash ? 1 : 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.12 }}
        className={`pointer-events-none fixed inset-0 modal-ink-wash ${zIndex}`}
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
