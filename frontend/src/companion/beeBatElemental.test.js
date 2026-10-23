import { describe, expect, it } from 'vitest';
import { resolveCompanionAppearance, validateAssetPackManifest } from '@abby-assets/contracts';
import activeLock from '../../assets.lock.json';
import support from '../../../shared/catalog/asset-support.json';
import { companionLifecycle } from './lifecycle';
import { elementalEvolutionStages, elementalFamilyId, isElementalCompanion, resolveElementalAppearance,
  resolveElementalPreviewAppearance, stagedElementalRelease } from './sharedElementalRelease';
import { resolveElementalCatalogIcon, resolveElementalPortrait } from './sharedElementalPortraits';
import { stagedElementalFixture } from '../test/elementalReleaseFixture';
import { BEE_BAT_FAMILY, BEE_BAT_MANIFEST_SHA256, BEE_BAT_MOTIONS, BEE_BAT_REVIEW_ICONS, stagedBeeBatFixture } from '../test/beeBatReleaseFixture';

const stages = ['baby', 'middle', 'grown'];
const appearances = Object.keys(BEE_BAT_MOTIONS).flatMap((species) => ['fire', 'ice'].flatMap((potion) => stages.map((stage) => [species, potion, stage])));
const creature = (species, potion, stage = 'baby') => ({ id: 19, species: { slug: species, sprite_key: species }, potion: { slug: potion },
  lifecycle_stage: stage, evolved_to_mount: stage === 'grown' });
const egg = (species) => ({ item_type: 'egg', slug: `${species}-egg`, pet_species_slug: species, metadata: { species } });

function evaluationMaps() {
  const staged = stagedBeeBatFixture();
  const pin = { family_id: BEE_BAT_FAMILY, release_version: '1.0.0', manifest_sha256: BEE_BAT_MANIFEST_SHA256,
    directory: `${BEE_BAT_FAMILY}/1.0.0/${BEE_BAT_MANIFEST_SHA256}` };
  const prefix = `../avatar/shared/${pin.directory}/`;
  return { ...staged, pin, manifests: { [`${prefix}manifest.json`]: staged.release },
    urls: Object.fromEntries(staged.release.files.map(({ path }) => [`${prefix}${path}`, staged.resolveUrl(path)])),
    indexes: { [`${prefix}manifest.json`]: staged.manifestUrl } };
}

describe('private Bee/Bat elemental presentation preparation', () => {
  it('resolves all twelve exact appearances and every native binding only from the supplied release', () => {
    const staged = stagedBeeBatFixture();
    expect(validateAssetPackManifest(staged.release)).toBe(staged.release);
    const motions = appearances.flatMap(([species, potion, stage]) => {
      expect(elementalFamilyId(species)).toBe(BEE_BAT_FAMILY);
      expect(isElementalCompanion({ slug: species, sprite_key: species }, { slug: potion })).toBe(true);
      const appearance = resolveElementalAppearance(creature(species, potion, stage), 'pet', staged);
      expect(appearance).toMatchObject({ key: `${species}-${potion}-${stage}`, stage, defaultVariantId: 'source-idle',
        defaultAction: 'idle', framing: 'roster', playLabel: 'Fly together', selection: { family_id: BEE_BAT_FAMILY, potion_slug: potion } });
      expect(appearance.motions.map(({ motion }) => motion)).toEqual(BEE_BAT_MOTIONS[species][stage]);
      expect(new Set(appearance.motions.map(({ id }) => id)).size).toBe(appearance.motions.length);
      for (const motion of appearance.motions) {
        const resolved = resolveCompanionAppearance(staged.release, { ...appearance.selection, motion: motion.motion });
        expect(motion).toMatchObject({ id: motion.motion, variantId: `source-${motion.motion}`, action: motion.motion,
          clip: resolved.variant.animations.actions[resolved.action], url: staged.resolveUrl(resolved.variant.file) });
      }
      expect(resolveElementalPreviewAppearance(egg(species), stage, { slug: potion }, staged).key).toBe(appearance.key);
      expect(elementalEvolutionStages(creature(species, potion, stage))).toEqual([]);
      return appearance.motions;
    });
    expect(motions).toHaveLength(130);
    expect(motions.filter(({ variantId }) => variantId === 'source-spin-attack-attack')).toHaveLength(2);
    expect(staged.release.appearance_bindings.transitions).toEqual([]);
    expect(staged.release.relationships).toEqual([]);
  });

  it.each(appearances)('uses the exact %s %s %s portrait without native-motion or Base fallback', (species, potion, stage) => {
    const staged = stagedBeeBatFixture(), suffix = stage === 'baby' ? '' : stage === 'middle' ? '-middle' : '-mount';
    const portraitId = `${species}-${potion}-${stage}-portrait`;
    const portrait = resolveElementalPortrait(`${species}${suffix}`, potion, staged);
    expect(portrait).toMatchObject({ frames: 1, label: `Synthetic ${portraitId}` });
    expect(resolveElementalCatalogIcon(portraitId, staged)).toEqual(portrait);
    expect(resolveElementalPortrait(`${species}${suffix}`, 'base', staged)).toBeNull();
    expect(resolveElementalPortrait(`${species}${suffix}`, potion, stagedElementalFixture())).toBeNull();
    expect(resolveElementalCatalogIcon(`source-${stage}`, staged)).toBeNull();
  });

  it.each(BEE_BAT_REVIEW_ICONS)('selects the exact %s review image without assigning a challenge', (id) => {
    expect(resolveElementalCatalogIcon(id, stagedBeeBatFixture())).toMatchObject({ label: `Synthetic ${id}`, frames: 1 });
    expect(resolveElementalCatalogIcon(id, stagedElementalFixture(true))).toBeNull();
  });

  it('requires the verified evaluation pin, complete inventory and declared v1 bindings', () => {
    const { release, pin, manifests, urls, indexes } = evaluationMaps();
    const resolve = (available = manifests, files = urls, lock = { releases: [pin] }, manifestUrls = indexes) =>
      stagedElementalRelease(available, files, lock, manifestUrls, BEE_BAT_FAMILY);
    expect(resolve()?.release).toBe(release);
    for (const field of ['manifest_sha256', 'release_version', 'directory']) {
      expect(resolve(manifests, urls, { releases: [{ ...pin, [field]: 'wrong' }] })).toBeNull();
    }
    const manifestKey = Object.keys(manifests)[0];
    expect(resolve({ [manifestKey]: { ...release, appearance_bindings: null } })).toBeNull();
    expect(resolve(manifests, urls, { releases: [pin] }, {})).toBeNull();
    expect(resolve(manifests, Object.fromEntries(Object.entries(urls).slice(1)))).toBeNull();
    expect(resolve(manifests, urls, activeLock)).toBeNull();
  });

  it('keeps acquisition and default runtime delivery unavailable while preserving natural eggs and Base names', () => {
    expect(activeLock.releases).toHaveLength(12);
    expect(activeLock.releases.some(({ family_id }) => family_id === BEE_BAT_FAMILY)).toBe(false);
    expect(support.pets.reduce((count, { potion_slugs }) => count + potion_slugs.length, 0)).toBe(23);
    for (const species of Object.keys(BEE_BAT_MOTIONS)) {
      expect(support.pets.find(({ species_slug }) => species_slug === species).potion_slugs).toEqual(['base']);
      for (const potion of ['fire', 'ice']) {
        expect(resolveElementalAppearance(creature(species, potion))).toBeNull();
        expect(resolveElementalPreviewAppearance(egg(species), 'baby', { slug: potion })).toBeNull();
        expect(resolveElementalPortrait(species, potion)).toBeNull();
      }
      const names = species === 'meshtint-bee' ? [null, 'Bee', 'Bumble', 'Sting'] : [null, 'Bat', 'Vampire Bat', 'Bat Lord'];
      for (const potion of ['base', 'fire', 'ice']) {
        expect(companionLifecycle({ slug: species, sprite_key: species }, { slug: potion }).map(({ form }) => form)).toEqual(names);
      }
      expect(resolveElementalPreviewAppearance({ ...egg(species), slug: `${species}-fire-egg` }, 'baby', { slug: 'fire' }, stagedBeeBatFixture())).toBeNull();
    }
    for (const id of BEE_BAT_REVIEW_ICONS) expect(resolveElementalCatalogIcon(id)).toBeNull();
  });

  it('rejects unsupported species, potion, stage, family, missing idle binding and missing portrait files', () => {
    const staged = stagedBeeBatFixture(), species = 'meshtint-bee', owned = creature(species, 'fire');
    expect(resolveElementalAppearance({ ...owned, species: { ...owned.species, sprite_key: 'meshtint-bat' } }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(creature(species, 'base'), 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...owned, lifecycle_stage: 'egg' }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(owned, 'pet', stagedElementalFixture(true))).toBeNull();
    expect(resolveElementalPreviewAppearance({ ...egg(species), metadata: { species: 'meshtint-bat' } }, 'baby', { slug: 'fire' }, staged)).toBeNull();
    staged.release.appearance_bindings.stages = staged.release.appearance_bindings.stages.filter((binding) => !(binding.species_slug === species
      && binding.potion_slug === 'fire' && binding.lifecycle_stage === 'baby' && binding.motion === 'idle'));
    expect(resolveElementalAppearance(owned, 'pet', staged)).toBeNull();
    expect(resolveElementalPortrait(species, 'fire', staged)).toBeNull();
    expect(resolveElementalPortrait('meshtint-bat', 'ice', { ...stagedBeeBatFixture(), resolveUrl: () => null })).toBeNull();
  });
});
