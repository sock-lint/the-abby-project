import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import { Crown, Sparkles, Egg, Coins, Map as MapIcon } from 'lucide-react';

import Button from '../../components/Button';
import RpgSprite from '../../components/rpg/RpgSprite';
import usePhasedSequence from './celebration/usePhasedSequence';
import SparkleBurst from './celebration/SparkleBurst';
import PotionAura from './celebration/PotionAura';

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

// Phase timings per mode (ms). The terminal phase is `phases.length` and
// always contains the "settled" state of the celebration. Tuned to land
// near 2.4–2.6s — the same wallclock as RareDropReveal so the cohort of
// "earned moment" surfaces all read at the same intensity.
const HATCH_PHASES = [800, 400, 1200];   // wobble → flash → reveal
const EVOLVE_PHASES = [400, 800, 300];   // hold → charge → flash (then settle)
const BREED_PHASES = [800, 400, 1200];   // converge → flash → reveal
const EXPEDITION_PHASES = [600, 400, 1200]; // approach → flash → reveal loot

/**
 * PetCeremonyModal — one-shot reveal for hatch, evolve, and breed moments.
 *
 *  mode="hatch":   shows the new pet emerging from a wobbling egg.
 *                  Pass `pet={{species:{name,sprite_key,icon}, potion:{name,slug}}}`.
 *
 *  mode="evolve":  shows the base pet charging up, flashing, and
 *                  resolving into its mount form with a gold sparkle.
 *                  Pass `species={{name,sprite_key,icon}}`, `potion={{name,slug}}`.
 *
 *  mode="breed":   shows the two parent mounts converging, then the
 *                  resulting egg + potion appearing in their place.
 *                  Pass `parents=[{species,potion}, {species,potion}]` and
 *                  `result={egg_item_*, potion_item_*, chromatic, ...}`.
 *
 * Tap anywhere or the dismiss button to close. Respects
 * ``prefers-reduced-motion``: the phased sequence collapses to its
 * terminal state instantly, sprites swap without animation, and
 * sparkles/flashes are skipped entirely.
 *
 * The component is presentational — no API calls. Callers handle
 * success bookkeeping (refetch, refresh, etc.) before mounting it.
 */
export default function PetCeremonyModal({ mode, pet, species, potion, parents, result, expedition, onDismiss }) {
  const titleId = useId();
  const reduced = usePrefersReducedMotion();

  const isHatch = mode === 'hatch';
  const isEvolve = mode === 'evolve';
  const isBreed = mode === 'breed';
  const isExpedition = mode === 'expedition_return';
  // Hooks must run unconditionally — phases falls back to HATCH for unknown
  // modes; the unknown branch returns null below after the hook calls.
  const phases = isEvolve
    ? EVOLVE_PHASES
    : isBreed
      ? BREED_PHASES
      : isExpedition
        ? EXPEDITION_PHASES
        : HATCH_PHASES;
  const phase = usePhasedSequence(phases, { reduced });
  if (!isHatch && !isEvolve && !isBreed && !isExpedition) return null;

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
        className="relative parchment-bg-aged p-8 text-center max-w-sm w-[90%] rounded-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {isHatch && (
          <HatchSequence
            pet={pet}
            phase={phase}
            reduced={reduced}
            titleId={titleId}
            onDismiss={onDismiss}
          />
        )}
        {isEvolve && (
          <EvolveSequence
            species={species}
            potion={potion}
            phase={phase}
            reduced={reduced}
            titleId={titleId}
            onDismiss={onDismiss}
          />
        )}
        {isBreed && (
          <BreedSequence
            parents={parents}
            result={result}
            phase={phase}
            reduced={reduced}
            titleId={titleId}
            onDismiss={onDismiss}
          />
        )}
        {isExpedition && (
          <ExpeditionReturnSequence
            expedition={expedition}
            phase={phase}
            reduced={reduced}
            titleId={titleId}
            onDismiss={onDismiss}
          />
        )}
      </motion.div>
    </div>
  );

  return createPortal(content, document.body);
}

// ─── Hatch ───────────────────────────────────────────────────────────────

function HatchSequence({ pet, phase, reduced, titleId, onDismiss }) {
  const speciesName = pet?.species?.name;
  const potionName = pet?.potion?.name;
  const potionSlug = pet?.potion?.slug;
  const headline = `${potionName} ${speciesName}`;

  // phase semantics:  0 = wobble, 1 = flash, 2 = reveal, 3 = settled
  const showEgg = phase < 2 && !reduced;
  const showFlash = phase === 1 && !reduced;
  const showPet = reduced || phase >= 2;

  return (
    <>
      <div className="flex items-center justify-center gap-2 text-sheikah-teal-deep">
        <Sparkles size={18} aria-hidden="true" />
        <div className="font-script text-base">a companion is born</div>
      </div>
      <div className="relative mt-4 flex items-center justify-center" style={{ minHeight: 140 }}>
        {showFlash && (
          <div
            className="animate-cosmic-burst absolute inset-0 m-auto pointer-events-none"
            style={{
              width: 180, height: 180,
              borderRadius: '50%',
              background:
                'radial-gradient(circle, rgba(255,250,225,0.9) 0%, rgba(255,220,160,0.4) 40%, transparent 75%)',
            }}
            aria-hidden="true"
          />
        )}
        {showEgg && (
          <div className="animate-wobble-pulse">
            <RpgSprite
              spriteKey="big-egg"
              icon="🥚"
              size={96}
              alt="egg"
            />
          </div>
        )}
        {showPet && (
          <>
            {!reduced && <PotionAura potionSlug={potionSlug} size={170} intensity={1} />}
            <motion.div
              initial={reduced ? {} : { scale: 0, rotate: -10, opacity: 0 }}
              animate={{ scale: 1, rotate: 0, opacity: 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.55, type: 'spring', bounce: 0.4 }}
              className="relative"
            >
              <RpgSprite
                spriteKey={pet?.species?.sprite_key}
                icon={pet?.species?.icon}
                size={96}
                alt={speciesName || 'pet'}
                potionSlug={potionSlug}
              />
            </motion.div>
            {!reduced && <SparkleBurst count={10} radius={100} duration={1.2} />}
          </>
        )}
      </div>
      <h2
        id={titleId}
        className="mt-3 font-display italic text-2xl text-ink-primary leading-tight"
      >
        {headline}
      </h2>
      <p className="mt-1 font-script text-sm text-ink-whisper">has joined your party.</p>
      <div className="mt-6">
        <Button variant="primary" onClick={onDismiss}>
          Continue →
        </Button>
      </div>
    </>
  );
}

// ─── Evolve ──────────────────────────────────────────────────────────────

function EvolveSequence({ species, potion, phase, reduced, titleId, onDismiss }) {
  const speciesName = species?.name;
  const potionName = potion?.name;
  const potionSlug = potion?.slug;
  const headline = `${potionName} ${speciesName}`;

  // phase semantics:  0 = hold, 1 = charge, 2 = flash, 3 = settled (mount)
  const showBase = phase < 2 && !reduced;
  const showFlash = phase === 2 && !reduced;
  const showMount = reduced || phase >= 3;
  const charging = phase === 1 && !reduced;

  // Aura intensity ramps with the charge so the buildup reads as energy.
  const auraIntensity = reduced ? 0.7 : phase === 0 ? 0.35 : phase === 1 ? 1 : 0.7;

  return (
    <>
      <div className="flex items-center justify-center gap-2 text-sheikah-teal-deep">
        <Crown size={18} className="text-gold-leaf" aria-hidden="true" />
        <div className="font-script text-base">evolution complete</div>
      </div>
      <div className="relative mt-4 flex items-center justify-center" style={{ minHeight: 140 }}>
        {!reduced && phase < 3 && (
          <PotionAura potionSlug={potionSlug} size={180} intensity={auraIntensity} />
        )}
        {showFlash && (
          <div
            className="animate-cosmic-burst absolute inset-0 m-auto pointer-events-none"
            style={{
              width: 200, height: 200,
              borderRadius: '50%',
              background:
                'radial-gradient(circle, rgba(255,255,255,0.95) 0%, rgba(255,235,180,0.45) 35%, transparent 75%)',
            }}
            aria-hidden="true"
          />
        )}
        {showBase && (
          <div
            style={{ filter: charging ? 'brightness(1.6)' : undefined, transition: 'filter 600ms ease-out' }}
            className="relative"
          >
            <RpgSprite
              spriteKey={species?.sprite_key}
              icon={species?.icon}
              size={96}
              alt={speciesName || 'pet'}
              potionSlug={potionSlug}
            />
          </div>
        )}
        {showMount && (
          <>
            <motion.div
              initial={reduced ? {} : { scale: 1.25, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.6, type: 'spring', bounce: 0.3 }}
              className="relative animate-gilded-glint rounded-full"
              style={{ padding: 6 }}
            >
              <RpgSprite
                spriteKey={species?.sprite_key ? `${species.sprite_key}-mount` : null}
                fallbackSpriteKey={species?.sprite_key}
                icon={species?.icon}
                size={96}
                alt={speciesName || 'mount'}
                potionSlug={potionSlug}
              />
            </motion.div>
            {!reduced && (
              <SparkleBurst
                count={12}
                radius={110}
                duration={1.4}
                color="var(--color-gold-leaf)"
              />
            )}
          </>
        )}
      </div>
      <h2
        id={titleId}
        className="mt-3 font-display italic text-2xl text-ink-primary leading-tight"
      >
        {headline}
      </h2>
      <p className="mt-1 font-script text-sm text-ink-whisper">is ready to ride.</p>
      <div className="mt-6">
        <Button variant="primary" onClick={onDismiss}>
          Continue →
        </Button>
      </div>
    </>
  );
}

// ─── Breed ───────────────────────────────────────────────────────────────

function BreedSequence({ parents, result, phase, reduced, titleId, onDismiss }) {
  const [parentA, parentB] = parents || [];
  const eggSpriteKey = result?.egg_item_sprite_key;
  const eggIcon = result?.egg_item_icon || '🥚';
  const potionSpriteKey = result?.potion_item_sprite_key;
  const potionIcon = result?.potion_item_icon || '🧪';
  const eggName = result?.egg_item_name;
  const potionItemName = result?.potion_item_name;
  const chromatic = !!result?.chromatic;
  const resultPotionSlug = chromatic ? 'cosmic' : (result?.picked_potion_slug || null);

  // phase semantics:  0 = converge, 1 = flash, 2 = reveal, 3 = settled
  const showParents = phase < 2 && !reduced;
  const showFlash = phase === 1 && !reduced;
  const showResult = reduced || phase >= 2;

  return (
    <>
      <div className="flex items-center justify-center gap-2 text-sheikah-teal-deep">
        <Egg size={18} className="text-gold-leaf" aria-hidden="true" />
        <div className="font-script text-base">
          {chromatic ? 'a chromatic blessing' : 'a hybrid is conceived'}
        </div>
      </div>
      <div className="relative mt-4 flex items-center justify-center" style={{ minHeight: 140 }}>
        {showParents && parentA && parentB && (
          <>
            <motion.div
              initial={reduced ? {} : { x: -90, opacity: 0 }}
              animate={{ x: phase === 0 ? -10 : 0, opacity: 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.7, ease: 'easeOut' }}
              className="absolute"
            >
              <RpgSprite
                spriteKey={parentA?.species?.sprite_key ? `${parentA.species.sprite_key}-mount` : null}
                fallbackSpriteKey={parentA?.species?.sprite_key}
                icon={parentA?.species?.icon}
                size={72}
                alt={parentA?.species?.name || 'parent'}
                potionSlug={parentA?.potion?.slug}
              />
            </motion.div>
            <motion.div
              initial={reduced ? {} : { x: 90, opacity: 0 }}
              animate={{ x: phase === 0 ? 10 : 0, opacity: 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.7, ease: 'easeOut' }}
              className="absolute"
            >
              <RpgSprite
                spriteKey={parentB?.species?.sprite_key ? `${parentB.species.sprite_key}-mount` : null}
                fallbackSpriteKey={parentB?.species?.sprite_key}
                icon={parentB?.species?.icon}
                size={72}
                alt={parentB?.species?.name || 'parent'}
                potionSlug={parentB?.potion?.slug}
              />
            </motion.div>
          </>
        )}
        {showFlash && (
          <div
            className="animate-cosmic-burst absolute inset-0 m-auto pointer-events-none"
            style={{
              width: 200, height: 200,
              borderRadius: '50%',
              background: chromatic
                ? 'radial-gradient(circle, rgba(220,200,255,0.95) 0%, rgba(170,130,255,0.5) 35%, transparent 75%)'
                : 'radial-gradient(circle, rgba(255,250,225,0.9) 0%, rgba(255,220,160,0.4) 40%, transparent 75%)',
            }}
            aria-hidden="true"
          />
        )}
        {showResult && (
          <>
            {!reduced && (
              <PotionAura potionSlug={resultPotionSlug} size={170} intensity={chromatic ? 1 : 0.7} />
            )}
            <motion.div
              initial={reduced ? {} : { scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.55, type: 'spring', bounce: 0.4 }}
              className="relative flex items-center gap-4"
            >
              <RpgSprite
                spriteKey={eggSpriteKey || 'big-egg'}
                icon={eggIcon}
                size={72}
                alt={eggName || 'egg'}
              />
              <RpgSprite
                spriteKey={potionSpriteKey}
                icon={potionIcon}
                size={72}
                alt={potionItemName || 'potion'}
                potionSlug={resultPotionSlug}
              />
            </motion.div>
            {!reduced && (
              <SparkleBurst
                count={chromatic ? 14 : 8}
                radius={chromatic ? 130 : 100}
                duration={chromatic ? 1.6 : 1.2}
                color={chromatic ? 'rgba(190,150,255,0.95)' : 'var(--color-gold-leaf)'}
              />
            )}
          </>
        )}
      </div>
      <h2
        id={titleId}
        className="mt-3 font-display italic text-2xl text-ink-primary leading-tight"
      >
        {eggName}
      </h2>
      <p className="mt-1 font-script text-sm text-ink-whisper">
        {chromatic
          ? `with a Cosmic potion · the stars favored this pairing`
          : `paired with ${potionItemName}`}
      </p>
      {result?.cooldown_days != null && (
        <p className="mt-1 font-script text-tiny text-ink-whisper">
          parents resting for {result.cooldown_days} days
        </p>
      )}
      <div className="mt-6">
        <Button variant="primary" onClick={onDismiss}>
          Continue →
        </Button>
      </div>
    </>
  );
}

// ─── Expedition return ───────────────────────────────────────────────────

/**
 * The mount returns from its offline run. Phase semantics:
 *   0 = approach (sprite slides in from edge)
 *   1 = flash (loot drops at the mount's feet)
 *   2 = reveal (coin chip + item icons appear)
 *   3 = settled
 *
 * `expedition` shape (from ExpeditionService.claim or the toast claim flow):
 *   { coins_awarded, items: [{name, icon, sprite_key, rarity, quantity, salvaged_to_coins?}],
 *     mount: { species_name, species_sprite_key, species_icon, potion_name, potion_slug }, tier }
 */
function ExpeditionReturnSequence({ expedition, phase, reduced, titleId, onDismiss }) {
  const mount = expedition?.mount || {};
  const speciesName = mount.species_name;
  const speciesSpriteKey = mount.species_sprite_key;
  const speciesIcon = mount.species_icon;
  const potionSlug = mount.potion_slug;
  const items = expedition?.items || [];
  const coins = expedition?.coins_awarded ?? 0;
  const tier = expedition?.tier;

  const showApproach = phase < 2 && !reduced;
  const showFlash = phase === 1 && !reduced;
  const showLoot = reduced || phase >= 2;

  return (
    <>
      <div className="flex items-center justify-center gap-2 text-sheikah-teal-deep">
        <MapIcon size={18} aria-hidden="true" />
        <div className="font-script text-base">your mount has returned</div>
      </div>
      <div className="relative mt-4 flex items-center justify-center" style={{ minHeight: 140 }}>
        {showFlash && (
          <div
            className="animate-cosmic-burst absolute inset-0 m-auto pointer-events-none"
            style={{
              width: 180, height: 180,
              borderRadius: '50%',
              background:
                'radial-gradient(circle, rgba(255,250,225,0.85) 0%, rgba(255,220,160,0.4) 40%, transparent 75%)',
            }}
            aria-hidden="true"
          />
        )}
        {showApproach && (
          <motion.div
            initial={reduced ? {} : { x: -110, opacity: 0 }}
            animate={{ x: phase === 0 ? -10 : 0, opacity: 1 }}
            transition={reduced ? { duration: 0 } : { duration: 0.7, ease: 'easeOut' }}
            className="absolute"
          >
            <RpgSprite
              spriteKey={speciesSpriteKey ? `${speciesSpriteKey}-mount` : null}
              fallbackSpriteKey={speciesSpriteKey}
              icon={speciesIcon}
              size={96}
              alt={speciesName || 'mount'}
              potionSlug={potionSlug}
            />
          </motion.div>
        )}
        {showLoot && (
          <>
            {!reduced && <PotionAura potionSlug={potionSlug} size={170} intensity={0.7} />}
            <motion.div
              initial={reduced ? {} : { scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.55, type: 'spring', bounce: 0.4 }}
              className="relative flex items-center justify-center gap-3 flex-wrap"
            >
              <RpgSprite
                spriteKey={speciesSpriteKey ? `${speciesSpriteKey}-mount` : null}
                fallbackSpriteKey={speciesSpriteKey}
                icon={speciesIcon}
                size={72}
                alt={speciesName || 'mount'}
                potionSlug={potionSlug}
              />
              <div className="flex flex-col items-start gap-1">
                {coins > 0 && (
                  <span className="inline-flex items-center gap-1 font-script text-base text-gold-leaf">
                    <Coins size={14} aria-hidden="true" /> +{coins}
                  </span>
                )}
                {items.slice(0, 4).map((item, idx) => (
                  <span key={`${item.name}-${idx}`} className="inline-flex items-center gap-1 font-body text-tiny text-ink-secondary">
                    <span aria-hidden="true">{item.icon || '🎁'}</span>
                    <span>{item.name}</span>
                    {item.salvaged_to_coins ? (
                      <span className="text-gold-leaf">· salvaged +{item.salvaged_to_coins}c</span>
                    ) : item.quantity > 1 ? (
                      <span className="text-ink-whisper">×{item.quantity}</span>
                    ) : null}
                  </span>
                ))}
              </div>
            </motion.div>
            {!reduced && <SparkleBurst count={8} radius={100} duration={1.2} />}
          </>
        )}
      </div>
      <h2
        id={titleId}
        className="mt-3 font-display italic text-2xl text-ink-primary leading-tight"
      >
        {speciesName ? `${speciesName} is back` : 'Your mount returned'}
      </h2>
      <p className="mt-1 font-script text-sm text-ink-whisper">
        {tier ? `from a ${tier} expedition` : 'with stories and a satchel of finds'}
      </p>
      <div className="mt-6">
        <Button variant="primary" onClick={onDismiss}>
          Take the loot →
        </Button>
      </div>
    </>
  );
}
