import { useId } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

/**
 * QuillProgress — illuminated-manuscript variant of ProgressBar.
 *
 * Same ARIA contract as ProgressBar (role="progressbar", aria-valuenow/min/max,
 * aria-label). Framer Motion handles the tween between consecutive `value`
 * renders — a skill that jumps from 40 → 65 XP visibly inks in without
 * manual prev-value tracking. A translucent SVG overlay (`data-quill-texture`)
 * adds a hand-drawn quill feel without shifting layout.
 *
 * Use this whenever the context is "mastery / progression" (skill level,
 * category XP). Keep ProgressBar for generic progress (savings, assignments).
 */
export default function QuillProgress({
  value,
  max = 100,
  color = 'bg-sheikah-teal-deep',
  className = '',
  'aria-label': ariaLabel = 'Mastery progress',
}) {
  const uid = useId();
  const reduceMotion = useReducedMotion();

  const safeValue = max > 0 ? Math.min(max, Math.max(0, value)) : 0;
  const pct = max > 0 ? (safeValue / max) * 100 : 0;

  return (
    <div
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuenow={Math.round(safeValue)}
      aria-valuemin={0}
      aria-valuemax={max}
      className={`relative h-2.5 bg-ink-page-shadow/55 rounded-full overflow-hidden border border-ink-page-shadow/40 ${className}`}
    >
      <motion.div
        data-quill-fill="true"
        className={`absolute inset-y-0 left-0 ${color} rounded-full shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: reduceMotion ? 0 : 0.55, ease: [0.4, 0, 0.2, 1] }}
      />
      {/* Quill texture — a subtle nib-tip overlay that fades toward the leading
          edge, reading as wet ink on parchment. Ignored by the reader tree. */}
      <svg
        data-quill-texture="true"
        aria-hidden="true"
        className="absolute inset-0 h-full w-full pointer-events-none opacity-40 mix-blend-multiply"
        preserveAspectRatio="none"
        viewBox="0 0 100 10"
      >
        <defs>
          <linearGradient id={`quill-${uid}`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="rgba(45,31,21,0)" />
            <stop offset="55%" stopColor="rgba(45,31,21,0.15)" />
            <stop offset="100%" stopColor="rgba(45,31,21,0.35)" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="100" height="10" fill={`url(#quill-${uid})`} />
        <path
          d="M0 5 Q 25 3 50 5 T 100 5"
          stroke="rgba(45,31,21,0.12)"
          strokeWidth="0.5"
          fill="none"
        />
      </svg>
    </div>
  );
}
