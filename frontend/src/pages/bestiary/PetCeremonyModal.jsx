import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import { Crown, Sparkles } from 'lucide-react';

import Button from '../../components/Button';
import RpgSprite from '../../components/rpg/RpgSprite';

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
 * PetCeremonyModal — one-shot reveal for hatch and evolve moments.
 *
 *  mode="hatch":   shows the new pet sprite with a sparkle reveal.
 *                  Pass `pet={{species:{name,sprite_key,icon}, potion:{name,slug}}}`.
 *
 *  mode="evolve":  shows the evolved mount with a crown halo.
 *                  Pass `species={{name,sprite_key,icon}}`, `potion={{name,slug}}`.
 *
 * Tap anywhere or the dismiss button to close. Respects
 * ``prefers-reduced-motion`` (no scale-burst for those users).
 *
 * The component is presentational — no API calls. Callers handle
 * success bookkeeping (refetch, refresh, etc.) before mounting it.
 */
export default function PetCeremonyModal({ mode, pet, species, potion, onDismiss }) {
  const titleId = useId();
  const reduced = usePrefersReducedMotion();

  const isHatch = mode === 'hatch';
  const isEvolve = mode === 'evolve';

  const sprite = isHatch
    ? {
        key: pet?.species?.sprite_key,
        icon: pet?.species?.icon,
        speciesName: pet?.species?.name,
        potionSlug: pet?.potion?.slug,
        potionName: pet?.potion?.name,
      }
    : {
        // Mount sprites use the `${species.sprite_key}-mount` convention with
        // a base-species fallback baked into RpgSprite.
        key: species?.sprite_key ? `${species.sprite_key}-mount` : null,
        fallbackKey: species?.sprite_key,
        icon: species?.icon,
        speciesName: species?.name,
        potionSlug: potion?.slug,
        potionName: potion?.name,
      };

  if (!isHatch && !isEvolve) return null;

  const headline = isHatch
    ? `${sprite.potionName} ${sprite.speciesName}`
    : `${sprite.potionName} ${sprite.speciesName}`;
  const kicker = isHatch
    ? 'has joined your party.'
    : 'is ready to ride.';

  const content = (
    <div
      role="alertdialog"
      aria-labelledby={titleId}
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={onDismiss}
    >
      <div className="absolute inset-0 bg-[rgba(15,18,28,0.55)] backdrop-blur-sm" />
      <motion.div
        initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0 }}
        transition={reduced ? { duration: 0.15 } : { duration: 0.5, ease: 'easeOut' }}
        className="relative parchment-bg-aged p-8 text-center max-w-sm w-[90%] rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-center gap-2 text-sheikah-teal-deep">
          {isEvolve ? (
            <Crown size={18} className="text-gold-leaf" aria-hidden="true" />
          ) : (
            <Sparkles size={18} aria-hidden="true" />
          )}
          <div className="font-script text-base">
            {isHatch ? 'a companion is born' : 'evolution complete'}
          </div>
        </div>
        <motion.div
          initial={reduced ? {} : { scale: 0, rotate: -10 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={reduced ? { duration: 0 } : { delay: 0.2, duration: 0.5, type: 'spring' }}
          className="mt-4 flex items-center justify-center"
          style={{ minHeight: 96 }}
        >
          <RpgSprite
            spriteKey={sprite.key}
            fallbackSpriteKey={sprite.fallbackKey}
            icon={sprite.icon}
            size={96}
            alt={sprite.speciesName || 'pet'}
            potionSlug={sprite.potionSlug}
          />
        </motion.div>
        <h2
          id={titleId}
          className="mt-3 font-display italic text-2xl text-ink-primary leading-tight"
        >
          {headline}
        </h2>
        <p className="mt-1 font-script text-sm text-ink-whisper">{kicker}</p>
        <div className="mt-6">
          <Button variant="primary" onClick={onDismiss}>
            Continue →
          </Button>
        </div>
      </motion.div>
    </div>
  );

  return createPortal(content, document.body);
}
