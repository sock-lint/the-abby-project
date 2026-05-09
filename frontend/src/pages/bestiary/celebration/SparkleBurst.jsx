import { useMemo } from 'react';
import { motion } from 'framer-motion';

/**
 * Radial sparkle burst. N small luminous dots fly outward from center on
 * (slightly) randomized angles, fading as they travel. Purely decorative —
 * always ``aria-hidden`` and pointer-events-none so it never traps clicks
 * or pollutes the accessibility tree.
 *
 * The parent is expected to gate the mount on its own
 * prefers-reduced-motion check; this component renders the same way for
 * both groups (motion.div animations are no-op'd by the global media
 * query inside framer-motion's CSS bridge).
 */
export default function SparkleBurst({
  count = 8,
  radius = 90,
  duration = 1.2,
  color = 'var(--color-gold-leaf)',
  size = 6,
}) {
  const sparkles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => {
      const baseAngle = (i / count) * 2 * Math.PI;
      const jitter = (i % 2 === 0 ? 1 : -1) * 0.18;
      const angle = baseAngle + jitter;
      const r = radius * (0.7 + ((i * 37) % 100) / 250);
      const dotSize = size + ((i * 13) % 5);
      return {
        id: i,
        x: Math.cos(angle) * r,
        y: Math.sin(angle) * r,
        delay: ((i * 23) % 100) / 666,
        size: dotSize,
      };
    });
  }, [count, radius, size]);

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
    >
      {sparkles.map(({ id, x, y, delay, size: s }) => (
        <motion.div
          key={id}
          initial={{ x: 0, y: 0, opacity: 0, scale: 0.4 }}
          animate={{ x, y, opacity: [0, 1, 0], scale: [0.4, 1.1, 0.6] }}
          transition={{ duration, delay, ease: 'easeOut' }}
          style={{
            position: 'absolute',
            width: s,
            height: s,
            borderRadius: '50%',
            background: color,
            boxShadow: `0 0 ${s * 1.6}px ${color}`,
          }}
        />
      ))}
    </div>
  );
}
