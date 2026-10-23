import { useOptionalAuth } from '../hooks/useApi';
import { companionStage } from './lifecycle';

const REACHED = { baby: ['baby'], middle: ['baby', 'middle'], grown: ['baby', 'middle', 'grown'] };

// The owner's surprise rule: a child sees companion forms only for an exact
// species and potion appearance they hatched, and only stages it reached.
// Staff and parents keep their previews. Without an authenticated user (only
// isolated fixtures) the existing presentation is unchanged.
export function surpriseRestricted(user) {
  return !!user && user.is_staff !== true && user.role !== 'parent';
}

export function useSurpriseRestricted() {
  return surpriseRestricted(useOptionalAuth()?.user);
}

// Server-confirmed stages only: growth counters never unlock the next form.
export function reachedStages(creature, kind = 'pet') {
  if (!creature?.id || !creature.species) return [];
  return REACHED[companionStage(creature, kind)] || REACHED.baby;
}

// Child artwork needs a positive exact identity: a legacy potion with a
// null or blank slug never stands in for Base.
const slugOf = (value) => (typeof value?.slug === 'string' && value.slug.trim()) || null;

function sameAppearance(creature, species, potion) {
  const variant = slugOf(potion);
  return !!variant && !!slugOf(species) && slugOf(creature?.species) === slugOf(species)
    && slugOf(creature?.potion) === variant;
}

// Stages of one exact appearance reached by an owned pet or grown mount.
// Missing or failed stable data reveals nothing.
export function ownedAppearanceStages(stable, species, potion) {
  if (!stable) return [];
  const reached = new Set([
    ...(stable.pets || []).filter((pet) => sameAppearance(pet, species, potion)).flatMap((pet) => reachedStages(pet)),
    ...(stable.mounts || []).filter((mount) => sameAppearance(mount, species, potion)).flatMap((mount) => reachedStages(mount, 'mount')),
  ]);
  return ['baby', 'middle', 'grown'].filter((stage) => reached.has(stage));
}

// One owned creature of a species, shown in its own reached appearance.
export function ownedSpeciesCreature(stable, species) {
  const slug = slugOf(species);
  if (!stable || !slug) return null;
  const exact = (entry) => slugOf(entry?.species) === slug && !!slugOf(entry.potion);
  const mount = (stable.mounts || []).find(exact);
  if (mount) return { creature: mount, kind: 'mount' };
  const pet = (stable.pets || []).find((entry) => entry?.id && exact(entry));
  return pet ? { creature: pet, kind: 'pet' } : null;
}
