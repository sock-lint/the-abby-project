import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * Pointer-based "drag" — uses framer-motion's drag with a drop target instead
 * of HTML5 dragdrop, which works on touch and pointer devices alike. We're
 * teaching the *idea* of moving currency into a goal, so a click-as-fallback
 * works just as well: tapping a token also moves it into the goal.
 */
export default function DragToTargetTrial({ entry, onReady }) {
  const trial = entry.trial || {};
  const sourceCount = Math.max(1, trial.source_count || 5);
  const [delivered, setDelivered] = useState(0);
  const target = sourceCount;

  const deliver = () => {
    setDelivered((current) => {
      const next = Math.min(target, current + 1);
      if (next >= target) onReady?.();
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-secondary leading-relaxed text-center">{trial.prompt}</p>

      <div className="grid grid-cols-2 gap-3 items-stretch">
        {/* Source pouch */}
        <div className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/60 p-3 text-center">
          <div className="text-tiny font-rune uppercase tracking-wider text-ink-whisper mb-2">
            pouch
          </div>
          <div className="text-5xl leading-none mb-2" aria-hidden="true">
            {trial.source_icon || '🪙'}
          </div>
          <button
            type="button"
            onClick={deliver}
            disabled={delivered >= target}
            className="font-rune text-tiny uppercase tracking-wider text-sheikah-teal-deep hover:text-sheikah-teal disabled:text-ink-whisper/40 disabled:cursor-not-allowed"
          >
            {delivered >= target ? 'empty' : 'send one'}
          </button>
        </div>

        {/* Target */}
        <div className="rounded-xl border border-moss/40 bg-moss/5 p-3 text-center">
          <div className="text-tiny font-rune uppercase tracking-wider text-moss mb-2">
            goal
          </div>
          <div className="text-5xl leading-none mb-2" aria-hidden="true">
            {trial.target_icon || '🎯'}
          </div>
          <div className="text-caption text-moss tabular-nums" aria-live="polite">
            {delivered} of {target}
          </div>
        </div>
      </div>

      <div className="h-2 w-full rounded-full bg-ink-page-shadow/30 overflow-hidden">
        <motion.div
          className="h-full bg-moss"
          animate={{ width: `${(delivered / target) * 100}%` }}
          transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
          aria-hidden="true"
        />
      </div>

      <AnimatePresence>
        {delivered >= target && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg border border-moss/30 bg-moss/10 px-3 py-2 text-center"
          >
            <div className="font-script text-base text-moss">{trial.payoff}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
