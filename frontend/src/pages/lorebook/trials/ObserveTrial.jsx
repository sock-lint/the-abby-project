import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

export default function ObserveTrial({ entry, onReady }) {
  const trial = entry.trial || {};
  const [progress, setProgress] = useState(0);

  // Pin the latest onReady in a ref so the animation effect can keep its
  // mount-only deps array (don't want to restart the rAF on prop change)
  // while still firing whichever onReady the parent has passed *most
  // recently* — closing over the mount-time value would silently call a
  // stale callback after a re-render.
  const onReadyRef = useRef(onReady);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  useEffect(() => {
    let frame;
    let start;
    const duration = 2400;
    const tick = (timestamp) => {
      if (start === undefined) start = timestamp;
      const elapsed = timestamp - start;
      const ratio = Math.min(1, elapsed / duration);
      setProgress(ratio);
      if (ratio < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        onReadyRef.current?.();
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="space-y-4 text-center">
      <p className="text-sm text-ink-secondary leading-relaxed">{trial.prompt}</p>

      <div className="mx-auto h-3 w-full max-w-xs rounded-full bg-ink-page-shadow/30 overflow-hidden">
        <motion.div
          className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
          style={{ width: `${progress * 100}%` }}
          aria-hidden="true"
        />
      </div>

      <div className="font-script text-base text-sheikah-teal-deep">{trial.payoff}</div>
      {trial.caption && (
        <div className="text-caption italic text-ink-whisper leading-snug">
          {trial.caption}
        </div>
      )}

      <div className="text-tiny font-rune uppercase tracking-wider text-ink-whisper">
        {progress < 1 ? 'observing…' : 'witnessed'}
      </div>
    </div>
  );
}
