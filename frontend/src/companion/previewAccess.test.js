import { describe, expect, it } from 'vitest';
import { ownedAppearanceStages, ownedSpeciesCreature, reachedStages, surpriseRestricted } from './previewAccess';

const wolf = { slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf' };
const base = { slug: 'base' }, fire = { slug: 'fire' }, ice = { slug: 'ice' };
const pet = (over) => ({ id: 9, species: wolf, potion: base, lifecycle_stage: 'baby', growth_points: 10, evolved_to_mount: false, ...over });

describe('child surprise preview access', () => {
  it.each([
    ['a child', { role: 'child' }, true],
    ['a child without a staff flag value', { role: 'child', is_staff: false }, true],
    ['an account without a role', { is_staff: false }, true],
    ['a parent', { role: 'parent', is_staff: false }, false],
    ['staff', { role: 'child', is_staff: true }, false],
    ['no authenticated user', null, false],
  ])('restricts %s: %s', (_name, user, restricted) => {
    expect(surpriseRestricted(user)).toBe(restricted);
  });

  it.each([
    ['baby', pet(), 'pet', ['baby']],
    ['middle', pet({ lifecycle_stage: 'middle', growth_points: 65 }), 'pet', ['baby', 'middle']],
    ['100 growth without confirmed evolution', pet({ lifecycle_stage: 'middle', growth_points: 100 }), 'pet', ['baby', 'middle']],
    ['confirmed evolution', pet({ lifecycle_stage: 'grown', evolved_to_mount: true }), 'pet', ['baby', 'middle', 'grown']],
    ['a grown mount row', pet({ lifecycle_stage: undefined }), 'mount', ['baby', 'middle', 'grown']],
    ['an egg item', { id: 4, item_type: 'egg', pet_species_slug: 'meshtint-wolf' }, 'pet', []],
  ])('reaches only server-confirmed stages for %s', (_name, creature, kind, stages) => {
    expect(reachedStages(creature, kind)).toEqual(stages);
  });

  it('matches the exact species and potion appearance across pets and mounts', () => {
    const stable = { pets: [pet({ potion: fire })], mounts: [pet({ id: 10, potion: ice })] };
    expect(ownedAppearanceStages(stable, wolf, fire)).toEqual(['baby']);
    expect(ownedAppearanceStages(stable, wolf, ice)).toEqual(['baby', 'middle', 'grown']);
    expect(ownedAppearanceStages(stable, wolf, base)).toEqual([]);
    expect(ownedAppearanceStages(stable, wolf, undefined)).toEqual([]);
    expect(ownedAppearanceStages(stable, { slug: 'meshtint-bat' }, fire)).toEqual([]);
  });

  it.each([['a null', { slug: null }], ['a blank', { slug: '  ' }], ['a missing', null]])('never treats %s legacy potion slug as Base', (_name, potion) => {
    const stable = { pets: [pet({ potion })], mounts: [pet({ id: 10, potion })] };
    expect(ownedAppearanceStages(stable, wolf, base)).toEqual([]);
    expect(ownedAppearanceStages(stable, wolf, { slug: null })).toEqual([]);
    expect(ownedSpeciesCreature(stable, wolf)).toBeNull();
  });

  it('reveals nothing when ownership is missing or failed', () => {
    expect(ownedAppearanceStages(null, wolf, base)).toEqual([]);
    expect(ownedAppearanceStages(undefined, wolf, base)).toEqual([]);
    expect(ownedSpeciesCreature(null, wolf)).toBeNull();
  });

  it('chooses an owned creature of the species in its own appearance', () => {
    const fireBaby = pet({ potion: fire });
    expect(ownedSpeciesCreature({ pets: [fireBaby], mounts: [] }, wolf)).toEqual({ creature: fireBaby, kind: 'pet' });
    const mount = pet({ id: 11, potion: ice });
    expect(ownedSpeciesCreature({ pets: [fireBaby], mounts: [mount] }, wolf)).toEqual({ creature: mount, kind: 'mount' });
    expect(ownedSpeciesCreature({ pets: [fireBaby], mounts: [] }, { slug: 'meshtint-bat' })).toBeNull();
  });
});
