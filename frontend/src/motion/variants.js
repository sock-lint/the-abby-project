// Shared Framer Motion variants for the Hyrule Field Notes aesthetic.
// Imported by JournalShell, chapter hubs, and individual journal primitives
// so every page feels like the same book.

export const pageReveal = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
  exit:    { opacity: 0, y: -8, transition: { duration: 0.2 } },
};

export const inkBleed = {
  initial: { opacity: 0, filter: 'blur(3px)', y: 6 },
  animate: { opacity: 1, filter: 'blur(0px)', y: 0, transition: { duration: 0.45, ease: 'easeOut' } },
};

export const staggerChildren = {
  animate: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
};

export const staggerItem = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
};

export const waxSealStamp = {
  initial: { scale: 0.4, rotate: -20, opacity: 0 },
  animate: {
    scale: 1,
    rotate: 0,
    opacity: 1,
    transition: { type: 'spring', stiffness: 320, damping: 16 },
  },
};

export const runePulse = {
  animate: {
    opacity: [0.7, 1, 0.7],
    filter: [
      'drop-shadow(0 0 2px var(--color-sheikah-teal))',
      'drop-shadow(0 0 8px var(--color-sheikah-teal))',
      'drop-shadow(0 0 2px var(--color-sheikah-teal))',
    ],
    transition: { duration: 2.6, repeat: Infinity, ease: 'easeInOut' },
  },
};

export const flameFlicker = {
  animate: {
    rotate: [-1, 2, -1, 1, -1],
    scale: [1, 1.05, 0.98, 1.03, 1],
    opacity: [0.95, 1, 0.9, 1, 0.95],
    transition: { duration: 2.4, repeat: Infinity, ease: 'easeInOut' },
  },
};

export const slideUpSheet = {
  initial: { y: '100%' },
  animate: { y: 0, transition: { type: 'spring', damping: 30, stiffness: 300 } },
  exit: { y: '100%', transition: { duration: 0.2 } },
};

export const fadeBackdrop = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit:    { opacity: 0, transition: { duration: 0.15 } },
};
