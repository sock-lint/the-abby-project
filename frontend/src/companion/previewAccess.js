import { useEffect, useState } from 'react';
import { getStable } from '../api';
import { useOptionalAuth } from '../hooks/useApi';
import { companionStage } from './lifecycle';
import expansion from '../../../shared/catalog/elemental-expansion.json';
import beeBat from '../../../shared/catalog/elemental-bee-bat.json';

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

// One read per account while several surfaces mount together; nothing is
// cached afterwards, so a later mount sees fresh ownership.
const pendingStableReads = new Map();
function readStable(userId) {
  if (!pendingStableReads.has(userId)) {
    pendingStableReads.set(userId, getStable().finally(() => pendingStableReads.delete(userId)));
  }
  return pendingStableReads.get(userId);
}

// The child's own stable, read only when a surface needs it. Until it loads,
// and after a failed read, stable is null and reveals nothing.
export function useSurpriseOwnership(needed = true) {
  const user = useOptionalAuth()?.user;
  const restricted = surpriseRestricted(user);
  const userId = user?.id;
  const [read, setRead] = useState(null);
  useEffect(() => {
    if (!restricted || !needed) return undefined;
    let current = true;
    readStable(userId).then((stable) => { if (current) setRead({ userId, stable }); },
      () => { if (current) setRead({ userId, stable: null }); });
    return () => { current = false; };
  }, [restricted, needed, userId]);
  return { restricted, stable: read && read.userId === userId ? read.stable : null };
}

// Catalog challenge presentation tied to one exact appearance. Elemental
// challenge illustrations depict its Baby; these descriptions open with a
// clause naming a form other than the species name.
const CHALLENGE_ART = new Map([
  ['challenge-ember-nest', ['chick', 'fire']], ['challenge-frost-nest', ['chick', 'ice']],
  ['challenge-ember-trail', ['meshtint-wolf', 'fire']], ['challenge-frost-trail', ['meshtint-wolf', 'ice']],
  ...[expansion, beeBat].flatMap(({ families }) => families.flatMap(({ species_slug, challenges }) =>
    challenges.map(({ catalog_icon, potion_slug }) => [catalog_icon, [species_slug, potion_slug]]))),
]);
const CHALLENGE_COPY = new Map([
  ['Shadow Trail', ['meshtint-shadow', 'base', 'grown']],
  ['Ember Summit', ['meshtint-dragon', 'fire', 'baby']],
  ['Frost Summit', ['meshtint-dragon', 'ice', 'baby']],
]);

function reached(stable, [species, potion, stage]) {
  return ownedAppearanceStages(stable, { slug: species }, { slug: potion }).includes(stage);
}

function challengeRules(goal) {
  return {
    art: goal?.catalog_icon ? CHALLENGE_ART.get(goal.catalog_icon) : null,
    copy: goal && goal.origin !== 'parent' ? CHALLENGE_COPY.get(goal.name) : null,
  };
}

export function isSurpriseChallenge(goal) {
  const { art, copy } = challengeRules(goal);
  return !!(art || copy);
}

// For a child, hide an unowned appearance's challenge illustration and the
// description clause that names an unreached form. Parents and staff, and
// ordinary challenge artwork, are unchanged.
export function challengeSurprise(goal, restricted, stable) {
  const { art, copy } = challengeRules(goal);
  const hideArt = restricted && !!art && !reached(stable, [...art, 'baby']);
  const hideClause = restricted && !!copy && !reached(stable, copy);
  const description = hideClause && goal.description?.includes(': ')
    ? goal.description.slice(goal.description.indexOf(': ') + 2).replace(/^./, (letter) => letter.toUpperCase())
    : goal?.description;
  return { hideArt, description };
}

export function useChallengeSurprise(goal) {
  const { restricted, stable } = useSurpriseOwnership(isSurpriseChallenge(goal));
  return challengeSurprise(goal, restricted, stable);
}
