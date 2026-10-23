import { describe, expect, it } from 'vitest';
import { petSpriteKeys } from './petSpriteKeys';

describe('pet portrait state', () => {
  const chick = { id: 1, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, evolution_stage: 'fledgling', growth_points: 50, evolved_to_mount: false };

  it('uses exact roster stage portrait keys and never falls back to a different family or baby for an unknown stage', () => {
    const pet = { ...chick, species: { slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf' }, lifecycle_stage: 'middle' };
    expect(petSpriteKeys(pet)).toEqual({ spriteKey: 'meshtint-wolf-middle', fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...pet, lifecycle_stage: 'future-stage' })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...pet, lifecycle_stage: 'grown', evolved_to_mount: false })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...pet, species: { slug: 'wolf', sprite_key: 'meshtint-wolf' } })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
    expect(petSpriteKeys(pet, 'mount')).toEqual({ spriteKey: 'meshtint-wolf-mount', fallbackSpriteKey: null });
  });

  it('uses the intermediate portrait only for the exact server-confirmed Fledgling', () => {
    expect(petSpriteKeys(chick)).toEqual({ spriteKey: 'cute-chick-fledgling', fallbackSpriteKey: 'cute-chick' });
    expect(petSpriteKeys({ ...chick, evolution_stage: null })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...chick, evolution_stage: 'bird', growth_points: 100 })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...chick, species: { slug: 'fox', sprite_key: 'cute-chick' } })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
  });

  it.each(['fire', 'ice'])('uses the exact confirmed %s Chick and Wolf stages without a different-stage fallback', (slug) => {
    for (const [species, keys] of [
      [{ slug: 'chick', sprite_key: 'cute-chick' }, ['cute-chick', 'cute-chick-fledgling', 'cute-chick-mount']],
      [{ slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf' }, ['meshtint-wolf', 'meshtint-wolf-middle', 'meshtint-wolf-mount']],
      [{ slug: 'meshtint-dragon', sprite_key: 'meshtint-dragon' }, ['meshtint-dragon', 'meshtint-dragon-middle', 'meshtint-dragon-mount']],
      [{ slug: 'meshtint-mushroom', sprite_key: 'meshtint-mushroom' }, ['meshtint-mushroom', 'meshtint-mushroom-middle', 'meshtint-mushroom-mount']],
    ]) {
      const pet = { id: 1, species, potion: { slug }, lifecycle_stage: 'baby', growth_points: 100 };
      expect(petSpriteKeys(pet)).toEqual({ spriteKey: keys[0], fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, lifecycle_stage: 'middle' })).toEqual({ spriteKey: keys[1], fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, lifecycle_stage: 'grown' })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, evolved_to_mount: true })).toEqual({ spriteKey: keys[2], fallbackSpriteKey: null });
      expect(petSpriteKeys(pet, 'mount')).toEqual({ spriteKey: keys[2], fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, lifecycle_stage: undefined })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, species: { ...species, slug: 'wrong-species' } })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
    }
  });

  it.each(['meshtint-bee', 'meshtint-bat'].flatMap((species) => ['fire', 'ice'].map((potion) => [species, potion])))(
    'selects every confirmed %s %s portrait while rejecting mismatched identities and unsupported stages', (species, potion) => {
      const pet = { id: 19, species: { slug: species, sprite_key: species }, potion: { slug: potion }, lifecycle_stage: 'baby', growth_points: 100 };
      expect(petSpriteKeys(pet)).toEqual({ spriteKey: species, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, lifecycle_stage: 'middle' })).toEqual({ spriteKey: `${species}-middle`, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, lifecycle_stage: 'grown', evolved_to_mount: false })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, evolved_to_mount: true })).toEqual({ spriteKey: `${species}-mount`, fallbackSpriteKey: null });
      expect(petSpriteKeys(pet, 'mount')).toEqual({ spriteKey: `${species}-mount`, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, lifecycle_stage: undefined })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, species: { ...pet.species, slug: 'wrong-species' } })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, species: { ...pet.species, sprite_key: 'fox' } })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, potion: { slug: 'base' } })).toEqual({ spriteKey: species, fallbackSpriteKey: null });
      expect(petSpriteKeys({ ...pet, potion: { slug: 'unsupported' } })).toEqual({ spriteKey: null, fallbackSpriteKey: null });
    },
  );

  it('keeps a fully grown pet on its base portrait until the server confirms evolution', () => {
    expect(petSpriteKeys({ species: { sprite_key: 'cute-chick' }, growth_points: 100, evolved_to_mount: false }))
      .toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
  });

  it.each(['cute-chick', 'fox'])('uses %s own evolved key with its base fallback', (base) => {
    expect(petSpriteKeys({ species: { sprite_key: base }, evolved_to_mount: true }))
      .toEqual({ spriteKey: `${base}-mount`, fallbackSpriteKey: base });
  });

  it.each([null, {}, { species: { name: 'Chick', icon: '🐥' }, evolved_to_mount: true }])(
    'does not infer a species key from incomplete companion data (%j)', (pet) => {
      expect(petSpriteKeys(pet)).toEqual({ spriteKey: null, fallbackSpriteKey: null });
    },
  );
});
