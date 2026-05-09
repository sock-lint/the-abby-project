import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import { Sun } from 'lucide-react';

import Button from '../Button';

function usePrefersReducedMotion() {
  const [pref, setPref] = useState(() =>
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mql = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mql) return;
    const handler = (e) => setPref(e.matches);
    mql.addEventListener?.('change', handler);
    return () => mql.removeEventListener?.('change', handler);
  }, []);
  return pref;
}

/**
 * DailyChallengeClaimModal — one-shot reveal after the child claims their
 * "Today's Rite" reward. Replaces the prior silent inline RuneBadge so the
 * daily ritual feels like a felt moment.
 *
 * Presentational — DailyChallengeCard owns the claim API call and only
 * mounts this modal when the server actually awarded coins/XP this session
 * (already_claimed=false).
 */
export default function DailyChallengeClaimModal({ claim, challengeLabel, onDismiss }) {
  const titleId = useId();
  const reduced = usePrefersReducedMotion();

  const coins = claim?.coins ?? 0;
  const xp = claim?.xp ?? 0;

  const content = (
    <div
      role="alertdialog"
      aria-labelledby={titleId}
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={onDismiss}
    >
      <div className="absolute inset-0 bg-[rgba(204,170,92,0.25)] backdrop-blur-sm" />
      <motion.div
        initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0 }}
        transition={reduced ? { duration: 0.15 } : { duration: 0.5 }}
        className="relative parchment-bg-aged p-8 text-center max-w-sm w-[88%] rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <Sun
          size={56}
          className="mx-auto text-gold-leaf"
          aria-hidden="true"
        />
        <h2
          id={titleId}
          className="mt-3 font-serif text-2xl text-ink-primary"
        >
          Rite complete
        </h2>
        {challengeLabel && (
          <p className="mt-1 font-script text-sm text-ink-whisper">
            {challengeLabel}
          </p>
        )}
        <p className="mt-4 font-display italic text-2xl text-gold-leaf">
          +{coins} coins · +{xp} XP
        </p>
        <p className="mt-2 font-script text-xs text-ink-whisper">
          a fresh rite opens at the next dawn.
        </p>
        <div className="mt-6">
          <Button variant="primary" onClick={onDismiss}>
            Turn the page →
          </Button>
        </div>
      </motion.div>
    </div>
  );

  return createPortal(content, document.body);
}
