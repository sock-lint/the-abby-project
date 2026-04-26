import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ScribeTrial({ entry, onReady }) {
  const trial = entry.trial || {};
  const minLength = Number.isFinite(trial.min_length) ? trial.min_length : 8;
  const [text, setText] = useState('');
  const [committed, setCommitted] = useState(false);

  const enough = text.trim().length >= minLength;

  const commit = () => {
    if (!enough || committed) return;
    setCommitted(true);
    onReady?.();
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-secondary leading-relaxed text-center">{trial.prompt}</p>

      <label className="block">
        <span className="sr-only">Inscribe a few words</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={4}
          maxLength={140}
          placeholder={trial.placeholder || 'Inscribe a few words…'}
          disabled={committed}
          className="w-full rounded-lg border border-ink-page-shadow bg-ink-page-aged/60 px-3 py-2 text-base font-script text-ink-primary placeholder:text-ink-whisper/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal/60 disabled:opacity-70"
        />
      </label>

      <div className="flex items-center justify-between text-caption text-ink-whisper">
        <span aria-live="polite">
          {committed
            ? 'Inscribed.'
            : enough
            ? 'Looks good.'
            : `Write at least ${minLength} characters.`}
        </span>
        <button
          type="button"
          onClick={commit}
          disabled={!enough || committed}
          className="font-rune text-tiny uppercase tracking-wider text-sheikah-teal-deep hover:text-sheikah-teal disabled:text-ink-whisper/40 disabled:cursor-not-allowed"
        >
          {committed ? 'committed' : 'commit to the page'}
        </button>
      </div>

      <AnimatePresence>
        {committed && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg border border-moss/30 bg-moss/10 px-3 py-2 text-center"
          >
            <div className="font-script text-base text-moss">{trial.payoff}</div>
            <div className="mt-1 text-caption italic text-ink-whisper">
              That's the journal — yours, and only one per day.
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
