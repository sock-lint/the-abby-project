import { motion } from 'framer-motion';

/**
 * ProgressBar — parchment track with a sheikah-teal fill by default.
 * Callers can override `color` with any Tailwind bg-* class.
 */
export default function ProgressBar({
  value,
  max = 100,
  color = 'bg-sheikah-teal-deep',
  className = '',
  'aria-label': ariaLabel = 'Progress',
}) {
  const safeValue = max > 0 ? Math.min(max, Math.max(0, value)) : 0;
  const pct = max > 0 ? (safeValue / max) * 100 : 0;
  return (
    <div
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuenow={Math.round(safeValue)}
      aria-valuemin={0}
      aria-valuemax={max}
      className={`h-2 bg-ink-page-shadow/60 rounded-full overflow-hidden ${className}`}
    >
      <motion.div
        className={`h-full ${color} rounded-full`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  );
}
