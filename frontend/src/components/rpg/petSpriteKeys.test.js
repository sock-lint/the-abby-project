import { describe, expect, it } from 'vitest';
import { petSpriteKeys } from './petSpriteKeys';

describe('pet portrait state', () => {
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
