import { describe, expect, it } from 'vitest';
import { resolveCompanionAppearance, validateAssetPackManifest } from '@abby-assets/contracts';
import activeLock from '../../assets.lock.json';
import support from '../../../shared/catalog/asset-support.json';
import preparation from '../../../shared/catalog/elemental-snake-hermit-crab.json';
import { companionLifecycle } from './lifecycle';
import { resolveAppearance } from './appearance';
import { elementalEvolutionStages, elementalFamilyId, isElementalCompanion, resolveElementalAppearance,
  resolveElementalPreviewAppearance, stagedElementalRelease } from './sharedElementalRelease';
import { resolveElementalCatalogIcon, resolveElementalPortrait } from './sharedElementalPortraits';
import { petSpriteKeys } from '../components/rpg/petSpriteKeys';
import { stagedElementalFixture } from '../test/elementalReleaseFixture';
import { SNAKE_CRAB_FAMILY, SNAKE_CRAB_SPECIES, SNAKE_CRAB_REVIEW_ICONS, stagedSnakeCrabFixture,
  snakeCrabCreature, snakeCrabEgg } from '../test/snakeCrabReleaseFixture';

const appearances = SNAKE_CRAB_SPECIES.flatMap((species) => ['fire', 'ice'].flatMap((potion) =>
  ['baby', 'middle', 'grown'].map((stage) => [species, potion, stage])));
const spriteSuffix = { baby: '', middle: '-middle', grown: '-mount' };

describe('prepared Snake/Hermit Crab elemental presentation', () => {
  it('resolves twelve exact appearances from explicitly isolated synthetic bindings, keeping native identities separate', () => {
    const staged = stagedSnakeCrabFixture();
    expect(validateAssetPackManifest(staged.release)).toBe(staged.release);
    for (const [species, potion, stage] of appearances) {
      const creature = snakeCrabCreature(species, potion, stage);
      expect(elementalFamilyId(species)).toBe(SNAKE_CRAB_FAMILY);
      expect(isElementalCompanion(creature.species, creature.potion)).toBe(true);
      const appearance = resolveElementalAppearance(creature, 'pet', staged);
      expect(appearance).toMatchObject({ key: `${species}-${potion}-${stage}`, stage, framing: 'roster',
        defaultVariantId: 'source-rest-take', defaultAction: 'rest_native', idleClip: 'Rest Native', playLabel: 'Walk together',
        selection: { family_id: SNAKE_CRAB_FAMILY, species_slug: species, potion_slug: potion, lifecycle_stage: stage } });
      expect(appearance.motions.map(({ id }) => id)).toEqual(['idle', 'rest-alias', 'walk-forward-in-place']);
      const [idle, alias, travel] = appearance.motions;
      expect(alias).toMatchObject({ variantId: idle.variantId, action: idle.action, clip: idle.clip, url: idle.url });
      expect(alias.id).not.toBe(idle.id);
      expect(travel).toMatchObject({ variantId: 'source-travel-take', action: 'travel_native', clip: 'Travel Native' });
      for (const motion of appearance.motions) {
        const resolved = resolveCompanionAppearance(staged.release, { ...appearance.selection, motion: motion.motion });
        expect(motion.variantId).toBe(resolved.variant.id);
        expect(motion.action).toBe(resolved.action);
      }
      expect(resolveElementalPreviewAppearance(snakeCrabEgg(species), stage, creature.potion, staged)?.key).toBe(appearance.key);
      expect(petSpriteKeys(creature)).toEqual({ spriteKey: `${species}${spriteSuffix[stage]}`, fallbackSpriteKey: null });
      expect(elementalEvolutionStages(creature)).toEqual([]);
    }
    expect(staged.release.appearance_bindings.transitions).toEqual([]);
  });

  it.each(appearances)('selects only the exact synthetic %s %s %s portrait', (species, potion, stage) => {
    const staged = stagedSnakeCrabFixture(), portraitId = `${species}-${potion}-${stage}-portrait`;
    const portrait = resolveElementalPortrait(`${species}${spriteSuffix[stage]}`, potion, staged);
    expect(portrait).toMatchObject({ frames: 1, label: `Synthetic ${portraitId}` });
    expect(resolveElementalCatalogIcon(portraitId, staged)).toEqual(portrait);
    expect(resolveElementalPortrait(`${species}${spriteSuffix[stage]}`, 'base', staged)).toBeNull();
    expect(resolveElementalPortrait(`${species}${spriteSuffix[stage]}`, potion, stagedElementalFixture())).toBeNull();
  });

  it.each(SNAKE_CRAB_REVIEW_ICONS)('resolves the %s planned review handle only in explicit synthetic staging', (id) => {
    expect(resolveElementalCatalogIcon(id, stagedSnakeCrabFixture())).toMatchObject({ frames: 1, label: `Synthetic ${id}` });
    expect(resolveElementalCatalogIcon(id, stagedElementalFixture())).toBeNull();
    expect(resolveElementalCatalogIcon(id)).toBeNull();
  });

  it('keeps normal delivery and acquisition disabled without an adopted digest, regardless of staged metadata or a fake pin', () => {
    expect(preparation.preparation).toEqual({ state: 'awaiting_private_assets', acquisition_active: false });
    expect(preparation.release.manifest_sha256).toBeNull();
    expect(activeLock.releases).toHaveLength(13);
    expect(activeLock.releases.some(({ family_id }) => family_id === SNAKE_CRAB_FAMILY)).toBe(false);
    expect(support.pets.reduce((count, { potion_slugs }) => count + potion_slugs.length, 0)).toBe(27);
    const staged = stagedSnakeCrabFixture(), fakeSha = staged.manifestSha256;
    const pin = { family_id: SNAKE_CRAB_FAMILY, release_version: '1.0.0', manifest_sha256: fakeSha,
      directory: `${SNAKE_CRAB_FAMILY}/1.0.0/${fakeSha}` };
    const prefix = `../avatar/shared/${pin.directory}/`, manifests = { [`${prefix}manifest.json`]: staged.release };
    const urls = Object.fromEntries(staged.release.files.map(({ path }) => [`${prefix}${path}`, staged.resolveUrl(path)]));
    const indexes = { [`${prefix}manifest.json`]: staged.manifestUrl };
    expect(stagedElementalRelease(manifests, urls, undefined, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, urls, { releases: [pin] }, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    for (const species of SNAKE_CRAB_SPECIES) {
      expect(support.pets.find(({ species_slug }) => species_slug === species).potion_slugs).toEqual(['base']);
      for (const potion of ['fire', 'ice']) for (const stage of ['baby', 'middle', 'grown']) {
        const creature = snakeCrabCreature(species, potion, stage);
        expect(resolveElementalAppearance(creature)).toBeNull();
        expect(resolveAppearance(creature)).toBeNull();
        expect(resolveElementalPreviewAppearance(snakeCrabEgg(species), stage, creature.potion)).toBeNull();
        expect(resolveElementalPortrait(`${species}${spriteSuffix[stage]}`, potion)).toBeNull();
      }
    }
  });

  it.each(SNAKE_CRAB_SPECIES)('preserves natural egg identity and form names for %s across Base/Fire/Ice', (species) => {
    const names = species === 'meshtint-snake' ? [null, 'Snakelet', 'Snake', 'Snake Naga'] : [null, 'Shell', 'Spike', 'Hermit King'];
    for (const potion of ['base', 'fire', 'ice']) {
      expect(companionLifecycle({ slug: species, sprite_key: species }, { slug: potion }).map(({ form }) => form)).toEqual(names);
    }
    const egg = snakeCrabEgg(species), staged = stagedSnakeCrabFixture();
    expect(resolveElementalPreviewAppearance({ ...egg, slug: `${species}-fire-egg` }, 'baby', { slug: 'fire' }, staged)).toBeNull();
    expect(resolveElementalPreviewAppearance({ ...egg, metadata: { species: 'meshtint-bee' } }, 'baby', { slug: 'fire' }, staged)).toBeNull();
  });

  it('fails explicitly for wrong identities, stages, absent bindings and missing models/portraits instead of substituting Base', () => {
    const species = 'meshtint-snake', owned = snakeCrabCreature(species, 'fire'), staged = stagedSnakeCrabFixture();
    expect(resolveElementalAppearance({ ...owned, species: { slug: species, sprite_key: 'meshtint-hermit-crab' } }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(snakeCrabCreature(species, 'base'), 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...owned, lifecycle_stage: 'egg' }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...owned, lifecycle_stage: 'grown' }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(owned, 'pet', stagedElementalFixture())).toBeNull();
    expect(resolveElementalAppearance(owned, 'pet', { ...staged, resolveUrl: () => null })).toBeNull();
    expect(resolveElementalPortrait(species, 'fire', { ...staged, resolveUrl: () => null })).toBeNull();
    const missingModel = staged.release.assets.find(({ id }) => id === `${species}-fire-baby`).variants[0].file;
    expect(resolveElementalAppearance(owned, 'pet', { ...staged, resolveUrl: (path) => path === missingModel ? null : staged.resolveUrl(path) })).toBeNull();
    staged.release.appearance_bindings.stages = staged.release.appearance_bindings.stages.filter((binding) => !(binding.species_slug === species
      && binding.potion_slug === 'fire' && binding.lifecycle_stage === 'baby' && binding.motion === 'idle'));
    expect(resolveElementalAppearance(owned, 'pet', staged)).toBeNull();
    expect(resolveElementalPortrait(species, 'fire', staged)).toBeNull();
    expect(resolveElementalCatalogIcon('source-rest-take', staged)).toBeNull();
  });
});
