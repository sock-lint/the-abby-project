import { describe, expect, it } from 'vitest';
import { birdFormName, birdStage, isBirdIdentity } from './birdEvolution';

const owned = { id: 1, species: { slug: 'chick', sprite_key: 'cute-chick', name: 'Chick' }, potion: { slug: 'base' } };

describe('Bird evolution presentation boundaries', () => {
  it('does not promote local growth or an unconfirmed Bird stage', () => {
    expect(birdStage({ ...owned, growth_points: 100 })).toBe('chick');
    expect(birdStage({ ...owned, evolution_stage: 'bird', evolved_to_mount: false })).toBeNull();
    expect(birdStage({ ...owned, evolution_stage: 'fledgling', growth_points: 50 })).toBe('fledgling');
    expect(birdStage({ ...owned, evolved_to_mount: true })).toBe('bird');
    expect(birdStage(owned, 'mount')).toBe('bird');
  });

  it('keeps unknown stages, missing ownership, other species and potion variants outside the bird family', () => {
    expect(birdStage({ ...owned, id: undefined })).toBeNull();
    expect(birdStage({ ...owned, evolution_stage: 'dragon' })).toBeNull();
    expect(isBirdIdentity({ slug: 'fox', sprite_key: 'cute-chick' }, owned.potion)).toBe(false);
    expect(birdFormName(owned.species, { slug: 'fire' }, 'fledgling')).toBe('Chick');
    expect(birdFormName({ name: 'Fox', slug: 'fox', sprite_key: 'fox' }, owned.potion, 'bird')).toBe('Fox');
  });
});
