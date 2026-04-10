import { motion } from 'framer-motion';

export default function ProgressBar({ value, max = 100, color = 'bg-amber-primary', className = '' }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className={`h-1.5 bg-forge-muted rounded-full overflow-hidden ${className}`}>
      <motion.div
        className={`h-full ${color} rounded-full`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
      />
    </div>
  );
}
