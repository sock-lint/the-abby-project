import { describe, expect, it } from 'vitest';
import { companionLifecycle, companionStage, companionStageLabel, eggSpecies } from './lifecycle';

const fox = { id: 2, species: { slug: 'fox', name: 'Fox', sprite_key: 'fox' }, potion: { slug: 'base' } };

describe('Companion family lifecycle', () => {
  it('reads generic server stages without deriving them from local growth', () => {
    expect(companionStage({ ...fox, growth_points: 100 })).toBe('baby');
    expect(companionStage({ ...fox, growth_points: 0, lifecycle_stage: 'middle' })).toBe('middle');
    expect(companionStage({ ...fox, lifecycle_stage: 'future-stage' })).toBeNull();
    expect(companionStageLabel({ ...fox, lifecycle_stage: 'middle' })).toBe('Middle');
  });

  it('requires confirmed evolution or an owned mount for the grown form', () => {
    expect(companionStage({ ...fox, lifecycle_stage: 'grown', evolved_to_mount: false })).toBeNull();
    expect(companionStage({ ...fox, evolved_to_mount: true })).toBe('grown');
    expect(companionStage(fox, 'mount')).toBe('grown');
    expect(companionStage(null)).toBeNull();
    expect(companionStage({ species: fox.species })).toBeNull();
  });

  it('keeps egg inventory separate from pet ownership and uses its declared species', () => {
    const egg = { item_type: 'egg', lifecycle_stage: 'egg', pet_species_slug: 'new-creature', pet_species_name: 'New creature' };
    expect(companionStage(egg)).toBe('egg');
    expect(eggSpecies(egg)).toEqual({ slug: 'new-creature', name: 'New creature' });
    expect(eggSpecies({ item_type: 'food', pet_species_slug: 'fox' })).toBeNull();
    expect(eggSpecies({ item_type: 'egg', name: 'Chick-looking Egg' })).toBeNull();
  });

  it.each([
    ['chick', 'cute-chick'],
    ['meshtint-bat', 'meshtint-bat'],
  ])('preserves the exact registered sprite identity of the %s egg for its form names', (slug, spriteKey) => {
    const egg = { item_type: 'egg', slug: `${slug}-egg`, pet_species_slug: slug, metadata: { species: slug } };
    expect(eggSpecies(egg)).toEqual({ slug, name: slug, sprite_key: spriteKey });
    for (const conflicting of [{ ...egg, slug: 'renamed-egg' }, { ...egg, metadata: { species: 'another-family' } }, { ...egg, pet_species_slug: 'another-family' }]) {
      expect(eggSpecies(conflicting)).not.toHaveProperty('sprite_key');
    }
  });

  it('limits prepared form names to the registry’s complete species and potion identity', () => {
    const species = { slug: 'chick', sprite_key: 'cute-chick' };
    expect(companionLifecycle(species, { slug: 'base' }).map(({ form }) => form)).toEqual([null, 'Chick', 'Fledgling', 'Bird']);
    for (const [otherSpecies, potion] of [[fox.species, { slug: 'base' }], [species, { slug: 'cosmic' }], [{ slug: 'fox', sprite_key: 'cute-chick' }, { slug: 'base' }]]) {
      expect(companionLifecycle(otherSpecies, potion).map(({ form }) => form)).toEqual([null, null, null, null]);
    }
  });

  it.each(['fire', 'ice'])('keeps the confirmed Chick and Wolf form names for %s without widening other families', (slug) => {
    expect(companionLifecycle({ slug: 'chick', sprite_key: 'cute-chick' }, { slug }).map(({ form }) => form))
      .toEqual([null, 'Chick', 'Fledgling', 'Bird']);
    expect(companionLifecycle({ slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf' }, { slug }).map(({ form }) => form))
      .toEqual([null, 'Wolf Pup', 'Wolf', 'Werewolf']);
    expect(companionLifecycle({ slug: 'meshtint-bat', sprite_key: 'meshtint-bat' }, { slug }).map(({ form }) => form))
      .toEqual([null, null, null, null]);
  });

  it('separates elemental Dragon names from the existing Base forms and preserves Mushroom form names', () => {
    const dragon = { slug: 'meshtint-dragon', sprite_key: 'meshtint-dragon' };
    expect(companionLifecycle(dragon, { slug: 'base' }).map(({ form }) => form)).toEqual([null, 'Dragon Spark', 'Dragon Fire', 'Dragon Inferno']);
    for (const slug of ['fire', 'ice']) {
      expect(companionLifecycle(dragon, { slug }).map(({ form }) => form)).toEqual([null, 'Dragonling', 'Dragon', 'Elder Dragon']);
      expect(companionLifecycle({ slug: 'meshtint-mushroom', sprite_key: 'meshtint-mushroom' }, { slug }).map(({ form }) => form)).toEqual([null, 'Mushroom', 'Fungi', 'Toadstool']);
      expect(companionLifecycle({ ...dragon, sprite_key: 'meshtint-mushroom' }, { slug }).map(({ form }) => form)).toEqual([null, null, null, null]);
    }
  });
});
