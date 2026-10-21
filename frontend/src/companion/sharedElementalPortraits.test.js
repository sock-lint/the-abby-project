import { describe, expect, it } from 'vitest';
import { resolveElementalCatalogIcon, resolveElementalPortrait } from './sharedElementalPortraits';

const appearances = [
  ['cute-chick', 'chick', 'baby'],
  ['cute-chick-fledgling', 'chick', 'middle'],
  ['cute-chick-mount', 'chick', 'grown'],
  ['meshtint-wolf', 'meshtint-wolf', 'baby'],
  ['meshtint-wolf-middle', 'meshtint-wolf', 'middle'],
  ['meshtint-wolf-mount', 'meshtint-wolf', 'grown'],
];
const uiImages = ['item-fire-potion', 'item-ice-potion', 'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail'];
function fixture() {
  const bindings = appearances.flatMap(([, species, stage]) => ['fire', 'ice'].map((potion) => ({
    species_slug: species, potion_slug: potion, lifecycle_stage: stage, motion: 'idle',
    asset_id: `${species}-${potion}-${stage}`, variant_id: 'source-idle', action: 'idle',
    portrait_asset_id: `${species}-${potion}-${stage}-portrait`, portrait_variant_id: 'icon',
  })));
  const ids = [...bindings.map(({ portrait_asset_id }) => portrait_asset_id), ...uiImages];
  const files = ids.map((_, index) => ({ path: `objects/${index.toString(16).padStart(64, '0')}.png`, media_type: 'image/png' }));
  const assets = ids.map((id, index) => ({ id, kind: 'image', label: id,
    variants: [{ id: 'icon', file: files[index].path, animations: null }] }));
  return { release: { assets, files, appearance_bindings: { schema_version: 1, stages: bindings } },
    resolveUrl: (path) => `/synthetic/elemental/${path}` };
}

describe('exact elemental portrait and catalog bindings', () => {
  it.each(['fire', 'ice'])('resolves all six %s stage portraits from appearance bindings using the declared icon', (potion) => {
    const staged = fixture();
    for (const [key, species, stage] of appearances) {
      const result = resolveElementalPortrait(key, potion, staged);
      expect(result).toMatchObject({ frames: 1, label: `${species}-${potion}-${stage}-portrait` });
      expect(result.url).toContain('/synthetic/elemental/objects/');
      expect(resolveElementalCatalogIcon(`${species}-${potion}-${stage}-portrait`, staged)).toEqual(result);
    }
  });

  it.each(uiImages)('resolves the exact typed %s catalog image', (id) => {
    expect(resolveElementalCatalogIcon(id, fixture())).toMatchObject({ label: id, frames: 1 });
  });

  it('keeps Base, unknown stages/species and model/native motion IDs outside this image adapter', () => {
    const staged = fixture();
    for (const key of ['wolf', 'meshtint-fox', 'cute-chick-middle', 'cute-chick-egg', 'toString', '__proto__', null]) {
      expect(resolveElementalPortrait(key, 'fire', staged)).toBeNull();
    }
    for (const potion of [null, 'base', 'shadow', 'source-idle']) {
      expect(resolveElementalPortrait('cute-chick', potion, staged)).toBeNull();
    }
    for (const id of ['chick-fire-baby', 'source-idle', 'item-base-potion', 'unknown-image']) {
      expect(resolveElementalCatalogIcon(id, staged)).toBeNull();
    }
    expect(resolveElementalPortrait('cute-chick', 'fire', null)).toBeNull();
    expect(resolveElementalCatalogIcon('item-fire-potion', null)).toBeNull();
  });

  it('does not fall back to Baby or Base when the exact Middle portrait is absent or malformed', () => {
    const staged = fixture();
    const binding = staged.release.appearance_bindings.stages.find((entry) => entry.species_slug === 'chick' && entry.potion_slug === 'fire' && entry.lifecycle_stage === 'middle');
    const asset = staged.release.assets.find(({ id }) => id === binding.portrait_asset_id);
    expect(resolveElementalPortrait('cute-chick-fledgling', 'fire', { ...staged, resolveUrl: () => null })).toBeNull();
    asset.variants[0].id = 'native';
    expect(resolveElementalPortrait('cute-chick-fledgling', 'fire', staged)).toBeNull();
    asset.variants[0].id = 'icon';
    staged.release.files.find(({ path }) => path === asset.variants[0].file).media_type = 'model/gltf-binary';
    expect(resolveElementalPortrait('cute-chick-fledgling', 'fire', staged)).toBeNull();
    asset.kind = 'companion';
    expect(resolveElementalCatalogIcon(asset.id, staged)).toBeNull();
  });
});
