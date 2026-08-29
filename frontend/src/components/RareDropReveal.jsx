import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles } from 'lucide-react';

import Button from './Button';
import RpgSprite from './rpg/RpgSprite';
import { hapticSuccess } from '../utils/haptics';
import { RARE_TIERS } from './rareDropTiers';
import {
  RARITY_BORDER_COLORS,
  RARITY_GLOW_COLORS,
  RARITY_TEXT_COLORS,
} from '../constants/colors';

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
 * RareDropReveal — full-screen one-shot reveal for rare/epic/legendary drops.
 *
 * Renders the topmost drop in `drops` as a center-screen card with a
 * rarity-coloured glow. Common/uncommon drops never enter this stream —
 * they continue to use the slide-in toast strip in DropToastStack so a
 * burst of low-rarity drops doesn't blanket the screen.
 *
 * The component is presentational: the parent owns the queue and calls
 * onDismiss(id) when the user taps Continue. The hook in DropToastStack
 * then advances the queue.
 */
export default function RareDropReveal({ drop, onDismiss }) {
  const titleId = useId();
  const reduced = usePrefersReducedMotion();

  useEffect(() => { hapticSuccess() }, []);

  const rarity = drop?.item_rarity;
  if (!RARE_TIERS.has(rarity)) return null;

  // Same rarity vocabulary the Satchel pills, badge halos and bestiary rings
  // speak — a kid learns the tier by its hue, so the reveal must not recolor it.
  const label = rarity.charAt(0).toUpperCase() + rarity.slice(1);
  const glow = `0 0 64px 10px color-mix(in srgb, ${RARITY_GLOW_COLORS[rarity]} 55%, transparent)`;

  const dismiss = () => onDismiss?.(drop.id);

  const content = (
    <AnimatePresence>
      <div
        role="alertdialog"
        aria-labelledby={titleId}
        aria-modal="true"
        className="fixed inset-0 z-50 flex items-center justify-center"
        onClick={dismiss}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="absolute inset-0 bg-[rgba(8,10,18,0.7)] backdrop-blur-sm"
          aria-hidden="true"
        />
        <motion.div
          initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.5, rotate: -8 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          exit={{ opacity: 0, scale: 0.85 }}
          transition={
            reduced
              ? { duration: 0.15 }
              : { duration: 0.55, ease: [0.22, 1.4, 0.36, 1] }
          }
          className={`relative parchment-bg-aged p-8 text-center max-w-sm w-[88%] rounded-2xl border-2 ${RARITY_BORDER_COLORS[rarity]}`}
          style={{ boxShadow: glow }}
          onClick={(e) => e.stopPropagation()}
        >
          <div
            className={`flex items-center justify-center gap-2 font-script text-base ${RARITY_TEXT_COLORS[rarity]}`}
          >
            <Sparkles size={18} aria-hidden="true" />
            <span className="uppercase tracking-widest">{label} drop</span>
            <Sparkles size={18} aria-hidden="true" />
          </div>
          <motion.div
            initial={reduced ? {} : { scale: 0 }}
            animate={{ scale: 1 }}
            transition={
              reduced ? { duration: 0 } : { delay: 0.2, duration: 0.5, type: 'spring' }
            }
            className="mt-5 mx-auto flex items-center justify-center"
            style={{ minHeight: 96 }}
          >
            <RpgSprite
              spriteKey={drop.item_sprite_key}
              icon={drop.item_icon}
              size={96}
              alt={drop.item_name}
            />
          </motion.div>
          <h2
            id={titleId}
            className="mt-3 font-display italic text-2xl text-ink-primary leading-tight"
          >
            {drop.item_name}
          </h2>
          {drop.was_salvaged ? (
            <p className="mt-1 font-script text-body text-ink-whisper">
              already in your collection — salvaged for coins.
            </p>
          ) : (
            <p className="mt-1 font-script text-body text-ink-whisper">
              added to your satchel.
            </p>
          )}
          <div className="mt-6">
            <Button variant="primary" onClick={dismiss}>
              Continue →
            </Button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );

  return createPortal(content, document.body);
}
