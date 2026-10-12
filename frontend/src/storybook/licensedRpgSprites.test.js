import { describe, expect, it } from 'vitest';
import presentation from './presentation.json';
import { resolveLicensedRpgSprite } from './licensedRpgSprites';

const manifest = {
  schema_version: presentation.schema_version,
  companion: {
    id: presentation.companion.id, art_key: 'chick', temporary: false, portrait: 'chick.png',
  },
};
const art = (name) => ({
  'chick.png': '/assets/synthetic-chick.png',
  'fledgling.png': '/assets/synthetic-fledgling.png',
  'bird.png': '/assets/synthetic-bird.png',
})[name];

describe('licensed RPG portraits', () => {
  it.each([
    ['cute-chick', '/assets/synthetic-chick.png'],
    ['cute-chick-mount', '/assets/synthetic-bird.png'],
  ])('maps %s to its matching portrait', (spriteKey, url) => {
    expect(resolveLicensedRpgSprite(spriteKey, manifest, art)).toEqual({ url, frames: 1 });
  });

  it.each(['dragon', 'wolf', 'companion', 'chick', 'cute-chick-extra', undefined])(
    'never reassigns Chick art to another sprite key (%s)', (spriteKey) => {
      expect(resolveLicensedRpgSprite(spriteKey, manifest, art)).toBeNull();
    },
  );

  it.each([
    undefined,
    {},
    { ...manifest, schema_version: 2 },
    { ...manifest, companion: { ...manifest.companion, id: 'another-preview' } },
    { ...manifest, companion: { ...manifest.companion, art_key: 'dragon' } },
    { ...manifest, companion: { ...manifest.companion, temporary: true } },
    { ...manifest, companion: { ...manifest.companion, portrait: 'bird.png' } },
  ])('requires a complete matching Chick overlay (%j)', (configured) => {
    expect(resolveLicensedRpgSprite('cute-chick', configured, art)).toBeNull();
    expect(resolveLicensedRpgSprite('cute-chick-mount', configured, art)).toBeNull();
  });

  it('keeps public builds usable when the staged images are absent', () => {
    expect(resolveLicensedRpgSprite('cute-chick', manifest)).toBeNull();
    expect(resolveLicensedRpgSprite('cute-chick', manifest, () => undefined)).toBeNull();
    expect(resolveLicensedRpgSprite('cute-chick-mount', manifest, (name) => name === 'bird.png' ? art(name) : undefined)).toBeNull();
  });

  it('keeps the pet portrait usable when the evolved portrait is missing', () => {
    const chickOnly = (name) => name === 'chick.png' ? art(name) : undefined;
    expect(resolveLicensedRpgSprite('cute-chick', manifest, chickOnly)).toEqual({ url: art('chick.png'), frames: 1 });
    expect(resolveLicensedRpgSprite('cute-chick-mount', manifest, chickOnly)).toBeNull();
  });
});
