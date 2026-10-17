import { describe, expect, it } from 'vitest';
import { petSpriteKeys } from './petSpriteKeys';

describe('pet portrait state', () => {
  const chick = { id: 1, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, evolution_stage: 'fledgling', growth_points: 50, evolved_to_mount: false };

  it('uses the intermediate portrait only for the exact server-confirmed Fledgling', () => {
    expect(petSpriteKeys(chick)).toEqual({ spriteKey: 'cute-chick-fledgling', fallbackSpriteKey: 'cute-chick' });
    expect(petSpriteKeys({ ...chick, evolution_stage: null })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...chick, evolution_stage: 'bird', growth_points: 100 })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...chick, species: { slug: 'fox', sprite_key: 'cute-chick' } })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
    expect(petSpriteKeys({ ...chick, potion: { slug: 'fire' } })).toEqual({ spriteKey: 'cute-chick', fallbackSpriteKey: null });
  });

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
