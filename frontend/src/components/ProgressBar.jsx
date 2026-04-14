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
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className={`h-2 bg-ink-page-shadow/60 rounded-full overflow-hidden ${className}`}>
      <motion.div
        className={`h-full ${color} rounded-full`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  );
}
