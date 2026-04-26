import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ChoiceTrial({ entry, onReady }) {
  const trial = entry.trial || {};
  const choices = Array.isArray(trial.choices) ? trial.choices : [];
  const [picked, setPicked] = useState(null);

  const pick = (choice) => {
    if (picked) return;
    setPicked(choice);
    onReady?.();
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-secondary leading-relaxed text-center">{trial.prompt}</p>

      <ul className="space-y-2 list-none p-0 m-0" role="list">
        {choices.map((choice) => {
          const active = picked && picked.label === choice.label;
          const dimmed = picked && !active;
          return (
            <li key={choice.label}>
              <button
                type="button"
                onClick={() => pick(choice)}
                disabled={!!picked}
                aria-pressed={active || undefined}
                className={`w-full flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal/60 ${
                  active
                    ? 'border-sheikah-teal-deep bg-sheikah-teal/10'
                    : dimmed
                    ? 'border-ink-page-shadow/40 bg-ink-page-aged/30 opacity-60'
                    : 'border-ink-page-shadow bg-ink-page-aged/60 hover:border-sheikah-teal-deep/60'
                }`}
              >
                <span className="text-3xl leading-none" aria-hidden="true">
                  {choice.icon || '✦'}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block font-display italic text-base text-ink-primary">
                    {choice.label}
                  </span>
                  {choice.outcome && (
                    <span className="block text-caption text-ink-whisper italic">
                      {choice.outcome}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <AnimatePresence>
        {picked && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg border border-sheikah-teal-deep/30 bg-sheikah-teal/5 px-3 py-2 text-center"
          >
            <div className="font-script text-base text-sheikah-teal-deep">{trial.payoff}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
