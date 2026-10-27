import { describe, expect, it } from 'vitest';
import { resolveCompanionAppearance, validateAssetPackManifest } from '@abby-assets/contracts';
import activeLock from '../../assets.lock.json';
import evaluationLock from '../../assets.snake-hermit-crab.evaluation.lock.json';
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

describe('canonical Snake/Hermit Crab elemental presentation', () => {
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

  it.each(SNAKE_CRAB_REVIEW_ICONS)('resolves the exact %s image from its supplied release', (id) => {
    expect(resolveElementalCatalogIcon(id, stagedSnakeCrabFixture())).toMatchObject({ frames: 1, label: `Synthetic ${id}` });
    expect(resolveElementalCatalogIcon(id, stagedElementalFixture())).toBeNull();
    expect(resolveElementalCatalogIcon(id, null)).toBeNull();
  });

  it('activates only the accepted canonical pin and four exact receiving pairs while missing files remain unavailable', () => {
    expect(preparation.preparation).toEqual({ state: 'active', acquisition_active: true,
      artwork_accepted: true, application_ids_agreed: true });
    expect(preparation.release.manifest_sha256).toBe('2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3');
    expect(activeLock.releases).toHaveLength(14);
    expect(activeLock.releases.find(({ family_id }) => family_id === SNAKE_CRAB_FAMILY)).toEqual(evaluationLock.releases[0]);
    expect(support.pets.reduce((count, { potion_slugs }) => count + potion_slugs.length, 0)).toBe(31);
    const staged = stagedSnakeCrabFixture(), fakeSha = staged.manifestSha256;
    const pin = { family_id: SNAKE_CRAB_FAMILY, release_version: '1.0.0', manifest_sha256: fakeSha,
      directory: `${SNAKE_CRAB_FAMILY}/1.0.0/${fakeSha}` };
    const prefix = `../avatar/shared/${pin.directory}/`, manifests = { [`${prefix}manifest.json`]: staged.release };
    const urls = Object.fromEntries(staged.release.files.map(({ path }) => [`${prefix}${path}`, staged.resolveUrl(path)]));
    const indexes = { [`${prefix}manifest.json`]: staged.manifestUrl };
    expect(stagedElementalRelease(manifests, urls, undefined, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, urls, { releases: [pin] }, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    const absent = stagedElementalRelease({}, {}, undefined, {}, SNAKE_CRAB_FAMILY);
    expect(absent).toBeNull();
    for (const species of SNAKE_CRAB_SPECIES) {
      expect(support.pets.find(({ species_slug }) => species_slug === species)).toMatchObject({
        potion_slugs: ['base', 'fire', 'ice'], potion_sources: { fire: SNAKE_CRAB_FAMILY, ice: SNAKE_CRAB_FAMILY },
      });
      for (const potion of ['fire', 'ice']) for (const stage of ['baby', 'middle', 'grown']) {
        const creature = snakeCrabCreature(species, potion, stage);
        expect(resolveElementalAppearance(creature, 'pet', absent)).toBeNull();
        expect(resolveAppearance(creature, 'pet', undefined, undefined, undefined, undefined, absent)).toBeNull();
        expect(resolveElementalPreviewAppearance(snakeCrabEgg(species), stage, creature.potion, absent)).toBeNull();
        expect(resolveElementalPortrait(`${species}${spriteSuffix[stage]}`, potion, absent)).toBeNull();
      }
    }
  });

  it('uses the canonical active lock for all twelve appearances and keeps the exact review pin independently usable', () => {
    const staged = stagedSnakeCrabFixture(), pin = evaluationLock.releases[0];
    expect(evaluationLock.releases).toHaveLength(1);
    expect(pin).toEqual({ ...preparation.release,
      directory: `${SNAKE_CRAB_FAMILY}/1.0.0/${preparation.release.manifest_sha256}` });
    const prefix = `../avatar/shared/${pin.directory}/`, manifests = { [`${prefix}manifest.json`]: staged.release };
    const urls = Object.fromEntries(staged.release.files.map(({ path }) => [`${prefix}${path}`, staged.resolveUrl(path)]));
    const indexes = { [`${prefix}manifest.json`]: staged.manifestUrl };
    expect(stagedElementalRelease(manifests, urls, evaluationLock, indexes, SNAKE_CRAB_FAMILY)?.release).toBe(staged.release);
    const canonical = stagedElementalRelease(manifests, urls, undefined, indexes, SNAKE_CRAB_FAMILY);
    expect(canonical?.release).toBe(staged.release);
    for (const [species, potion, stage] of appearances) {
      const creature = snakeCrabCreature(species, potion, stage);
      expect(resolveElementalAppearance(creature, 'pet', canonical)?.key).toBe(`${species}-${potion}-${stage}`);
      expect(resolveElementalPreviewAppearance(snakeCrabEgg(species), stage, creature.potion, canonical)?.key).toBe(`${species}-${potion}-${stage}`);
      expect(resolveElementalPortrait(`${species}${spriteSuffix[stage]}`, potion, canonical)).toMatchObject({ frames: 1 });
    }
    expect(stagedElementalRelease(manifests, urls, { releases: activeLock.releases.filter(({ family_id }) => family_id !== SNAKE_CRAB_FAMILY) },
      indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, {}, evaluationLock, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, urls, evaluationLock, {}, SNAKE_CRAB_FAMILY)).toBeNull();
    expect(stagedElementalRelease({ [`${prefix}manifest.json`]: { ...staged.release, appearance_bindings: null } }, urls,
      evaluationLock, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
    for (const field of ['manifest_sha256', 'release_version', 'directory']) {
      expect(stagedElementalRelease(manifests, urls, { releases: [{ ...pin, [field]: 'wrong' }] }, indexes, SNAKE_CRAB_FAMILY)).toBeNull();
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
