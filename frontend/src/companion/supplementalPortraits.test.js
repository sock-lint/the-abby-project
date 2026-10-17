import { describe, expect, it } from 'vitest';
import { resolveSupplementalPortrait, resolveSupplementalCatalogIcon } from './supplementalPortraits';

const urls = Object.fromEntries(['chick', 'chick-native', 'fledgling', 'fledgling-native', 'bird', 'bird-native', 'normal-egg']
  .map((name) => [`./supplemental/${name}.png`, `/${name}.png`]));

describe('Pinned supplemental portraits', () => {
  it('uses the supplied icon/native Bird images and single Normal Egg image', () => {
    expect(resolveSupplementalPortrait('cute-chick', 'icon', urls)?.url).toBe('/chick.png');
    expect(resolveSupplementalPortrait('cute-chick-fledgling', 'native', urls)?.url).toBe('/fledgling-native.png');
    expect(resolveSupplementalPortrait('cute-chick-mount', 'native', urls)?.url).toBe('/bird-native.png');
    expect(resolveSupplementalPortrait('chick-egg', 'native', urls)?.url).toBe('/normal-egg.png');
  });
  it('keeps unknown eggs, species and missing images on their own fallback', () => {
    for (const key of ['big-egg', 'meshtint-bat', 'wolf', 'training-dummy', 'Egg 07A']) {
      expect(resolveSupplementalPortrait(key, 'icon', urls)).toBeNull();
    }
    expect(resolveSupplementalPortrait('cute-chick', 'unknown', urls)).toBeNull();
    expect(resolveSupplementalPortrait('cute-chick', 'icon', {})).toBeNull();
  });
  it('maps only retained server catalog IDs to their supplied portraits', () => {
    expect(resolveSupplementalCatalogIcon('item-chick-egg', urls)?.url).toBe('/normal-egg.png');
    expect(resolveSupplementalCatalogIcon('portrait-chick', urls)?.url).toBe('/chick.png');
    expect(resolveSupplementalCatalogIcon('portrait-chick-grown', urls)?.url).toBe('/bird.png');
    for (const id of ['big-egg', 'chick', 'meshtint-training-dummy', 'portrait-wolf']) expect(resolveSupplementalCatalogIcon(id, urls)).toBeNull();
  });
});
