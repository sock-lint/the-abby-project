import { motion } from 'framer-motion';

/**
 * PageShell — root wrapper for page bodies. Replaces the copy-pasted
 * `<motion.div className="max-w-6xl mx-auto space-y-5">` pattern that every
 * page had been re-rolling. Owns the spine width, vertical rhythm, and the
 * fade-in animation.
 *
 * Outer page chrome (sticky header, bottom nav, FAB) AND outer horizontal
 * padding live in JournalShell (`px-4 md:px-6`). PageShell only owns inner
 * spine width + rhythm + entrance animation — adding px here would double-pad.
 *
 * Props:
 *   rhythm   - 'loose' | 'default' | 'tight' (default 'default')
 *              loose=space-y-6, default=space-y-5, tight=space-y-3
 *   width    - 'wide' | 'narrow' (default 'wide')
 *              wide=max-w-6xl, narrow=max-w-3xl (for Settings-style pages)
 *   animate  - boolean (default true). Set false to skip the fade-in for
 *              pages that already animate their own body.
 *   as       - element to render (default 'div'). Used when a page wants
 *              <main> semantics.
 */
const RHYTHM_CLASSES = {
  loose: 'space-y-6',
  default: 'space-y-5',
  tight: 'space-y-3',
};

const WIDTH_CLASSES = {
  wide: 'max-w-6xl',
  narrow: 'max-w-3xl',
};

export default function PageShell({
  children,
  rhythm = 'default',
  width = 'wide',
  animate = true,
  as = 'div',
  className = '',
  ...rest
}) {
  const rhythmClass = RHYTHM_CLASSES[rhythm] || RHYTHM_CLASSES.default;
  const widthClass = WIDTH_CLASSES[width] || WIDTH_CLASSES.wide;
  const combined = `${widthClass} mx-auto ${rhythmClass} ${className}`;

  if (!animate) {
    const Tag = as;
    return (
      <Tag className={combined} {...rest}>
        {children}
      </Tag>
    );
  }

  // Callers that supply their own variants / initial / animate take over
  // the motion config (e.g. dashboards using the ink-bleed variant). Otherwise
  // we apply the default page-reveal fade.
  const { variants, initial, animate: animateProp, transition, ...other } = rest;
  const MotionTag = motion[as] || motion.div;
  const motionConfig = variants
    ? { variants, initial: initial ?? 'initial', animate: animateProp ?? 'animate' }
    : {
        initial: initial ?? { opacity: 0, y: 8 },
        animate: animateProp ?? { opacity: 1, y: 0 },
        transition: transition ?? { duration: 0.25, ease: 'easeOut' },
      };
  return (
    <MotionTag className={combined} {...motionConfig} {...other}>
      {children}
    </MotionTag>
  );
}
