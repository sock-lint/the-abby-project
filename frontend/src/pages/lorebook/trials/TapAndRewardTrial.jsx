import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Button from '../../../components/Button';

export default function TapAndRewardTrial({ entry, onReady }) {
  const trial = entry.trial || {};
  const [tapped, setTapped] = useState(false);

  const handleTap = () => {
    if (tapped) return;
    setTapped(true);
    onReady?.();
  };

  return (
    <div className="space-y-4 text-center">
      <p className="text-sm text-ink-secondary leading-relaxed">{trial.prompt}</p>

      <div className="relative mx-auto h-40 w-40 rounded-full bg-ink-page-aged shadow-[inset_0_2px_8px_rgba(45,31,21,0.18),inset_0_-2px_4px_rgba(255,248,224,0.5)] flex items-center justify-center">
        {!tapped ? (
          <motion.button
            type="button"
            onClick={handleTap}
            whileTap={{ scale: 0.92 }}
            className="text-6xl leading-none focus:outline-none focus-visible:ring-4 focus-visible:ring-sheikah-teal/60 rounded-full p-3"
            aria-label={trial.prompt}
          >
            <span aria-hidden="true">{trial.target_icon || '🎯'}</span>
          </motion.button>
        ) : (
          <AnimatePresence>
            <motion.div
              key="reward"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', damping: 14, stiffness: 220 }}
              className="text-7xl leading-none"
            >
              <span aria-hidden="true">{trial.reward_icon || '✨'}</span>
            </motion.div>
          </AnimatePresence>
        )}
      </div>

      <AnimatePresence>
        {tapped && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-2"
          >
            <div className="font-script text-base text-sheikah-teal-deep">
              {trial.payoff}
            </div>
            <div className="text-caption italic text-ink-whisper">
              You felt it — that's what the page is teaching.
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!tapped && (
        <div className="text-caption italic text-ink-whisper">
          Tap to feel the mechanic in motion.
        </div>
      )}

      {/* Secondary "skip" affordance — kid can always finish without tapping. */}
      {!tapped && (
        <Button variant="ghost" size="sm" onClick={handleTap}>
          I get it — let me ink the page
        </Button>
      )}
    </div>
  );
}
