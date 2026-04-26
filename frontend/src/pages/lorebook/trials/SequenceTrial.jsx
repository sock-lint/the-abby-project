import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function SequenceTrial({ entry, onReady }) {
  const trial = entry.trial || {};
  const steps = Array.isArray(trial.steps) ? trial.steps : [];
  const [advanced, setAdvanced] = useState(0);

  const advance = () => {
    setAdvanced((current) => {
      const next = Math.min(steps.length, current + 1);
      if (next >= steps.length) onReady?.();
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-secondary leading-relaxed text-center">{trial.prompt}</p>

      <ol className="space-y-2 list-none p-0 m-0" role="list">
        {steps.map((step, index) => {
          const reached = index < advanced;
          const current = index === advanced;
          return (
            <motion.li
              key={step}
              initial={false}
              animate={{
                opacity: reached || current ? 1 : 0.5,
                scale: current ? 1.02 : 1,
              }}
              transition={{ duration: 0.25 }}
              className={`flex items-start gap-3 rounded-xl border px-3 py-2.5 ${
                reached
                  ? 'border-moss/40 bg-moss/5'
                  : current
                  ? 'border-sheikah-teal-deep/40 bg-sheikah-teal/5'
                  : 'border-ink-page-shadow/40 bg-ink-page-aged/30'
              }`}
            >
              <span
                className={`mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-rune text-tiny tabular-nums ${
                  reached
                    ? 'bg-moss text-ink-page'
                    : current
                    ? 'bg-sheikah-teal-deep text-ink-page'
                    : 'bg-ink-page-shadow/40 text-ink-whisper'
                }`}
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <span className="text-sm text-ink-primary leading-snug">{step}</span>
            </motion.li>
          );
        })}
      </ol>

      <div className="flex items-center justify-between text-caption text-ink-whisper">
        <span aria-live="polite" className="tabular-nums">
          {Math.min(advanced, steps.length)} of {steps.length}
        </span>
        <button
          type="button"
          onClick={advance}
          disabled={advanced >= steps.length}
          className="font-rune text-tiny uppercase tracking-wider text-sheikah-teal-deep hover:text-sheikah-teal disabled:text-ink-whisper/40 disabled:cursor-not-allowed"
        >
          {advanced >= steps.length ? 'sequence complete' : 'advance'}
        </button>
      </div>

      <AnimatePresence>
        {advanced >= steps.length && (
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
