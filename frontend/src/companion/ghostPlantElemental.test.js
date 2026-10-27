import { describe, expect, it } from 'vitest';
import { resolveCompanionAppearance, validateAssetPackManifest } from '@abby-assets/contracts';
import activeLock from '../../assets.lock.json';
import evaluationLock from '../../assets.ghost-potted-plant.evaluation.lock.json';
import support from '../../../shared/catalog/asset-support.json';
import preparation from '../../../shared/catalog/elemental-ghost-potted-plant.json';
import { resolveAppearance } from './appearance';
import { companionLifecycle } from './lifecycle';
import { challengeSurprise, isSurpriseChallenge, ownedAppearanceStages } from './previewAccess';
import { elementalEvolutionStages, elementalFamilyId, isElementalCompanion, resolveElementalAppearance,
  resolveElementalPreviewAppearance, stagedElementalRelease } from './sharedElementalRelease';
import { resolveElementalCatalogIcon, resolveElementalPortrait } from './sharedElementalPortraits';
import { petSpriteKeys } from '../components/rpg/petSpriteKeys';
import { stagedElementalFixture } from '../test/elementalReleaseFixture';
import { GHOST_PLANT_FAMILY, GHOST_PLANT_SPECIES, GHOST_PLANT_REVIEW_ICONS, stagedGhostPlantFixture,
  ghostPlantCreature, ghostPlantEgg } from '../test/ghostPlantReleaseFixture';

const stages = ['baby', 'middle', 'grown'];
const appearances = GHOST_PLANT_SPECIES.flatMap((species) => ['fire', 'ice'].flatMap((potion) =>
  stages.map((stage) => [species, potion, stage])));
const suffix = { baby: '', middle: '-middle', grown: '-mount' };

describe('Ghost/Potted Plant preparation with synthetic contract data only', () => {
  it('registers twelve explicit receiving appearances without confusing logical motions and native takes', () => {
    const staged = stagedGhostPlantFixture();
    expect(validateAssetPackManifest(staged.release)).toBe(staged.release);
    for (const [species, potion, stage] of appearances) {
      const creature = ghostPlantCreature(species, potion, stage);
      expect(elementalFamilyId(species)).toBe(GHOST_PLANT_FAMILY);
      expect(isElementalCompanion(creature.species, creature.potion)).toBe(true);
      const resolved = resolveElementalAppearance(creature, 'pet', staged);
      expect(resolved).toMatchObject({ key: `${species}-${potion}-${stage}`, stage, framing: 'roster',
        defaultVariantId: 'source-rest-take', defaultAction: 'rest_native', idleClip: 'Rest Native',
        selection: { family_id: GHOST_PLANT_FAMILY, species_slug: species, potion_slug: potion, lifecycle_stage: stage } });
      expect(resolved.motions.map(({ id }) => id)).toEqual(['idle', 'rest-alias', 'walk-forward-in-place']);
      const [idle, alias] = resolved.motions;
      expect(alias).toMatchObject({ variantId: idle.variantId, action: idle.action, clip: idle.clip, url: idle.url });
      expect(alias.id).not.toBe(idle.id);
      for (const motion of resolved.motions) {
        const native = resolveCompanionAppearance(staged.release, { ...resolved.selection, motion: motion.motion });
        expect(motion.variantId).toBe(native.variant.id);
        expect(motion.action).toBe(native.action);
      }
      expect(resolveElementalPreviewAppearance(ghostPlantEgg(species), stage, creature.potion, staged)?.key).toBe(resolved.key);
      expect(petSpriteKeys(creature)).toEqual({ spriteKey: `${species}${suffix[stage]}`, fallbackSpriteKey: null });
      expect(elementalEvolutionStages(creature)).toEqual([]);
    }
    expect(staged.release.appearance_bindings.transitions).toEqual([]);
  });

  it.each(appearances)('resolves only the explicitly supplied synthetic %s %s %s portrait', (species, potion, stage) => {
    const staged = stagedGhostPlantFixture(), id = `${species}-${potion}-${stage}-portrait`;
    const portrait = resolveElementalPortrait(`${species}${suffix[stage]}`, potion, staged);
    expect(portrait).toMatchObject({ frames: 1, label: `Synthetic ${id}` });
    expect(resolveElementalCatalogIcon(id, staged)).toEqual(portrait);
    expect(resolveElementalPortrait(`${species}${suffix[stage]}`, 'base', staged)).toBeNull();
    expect(resolveElementalPortrait(`${species}${suffix[stage]}`, potion, stagedElementalFixture())).toBeNull();
  });

  it.each(GHOST_PLANT_REVIEW_ICONS)('accepts the exact %s image identity only from its explicitly supplied family', (id) => {
    expect(resolveElementalCatalogIcon(id, stagedGhostPlantFixture())).toMatchObject({ frames: 1, label: `Synthetic ${id}` });
    expect(resolveElementalCatalogIcon(id, stagedElementalFixture())).toBeNull();
    expect(resolveElementalCatalogIcon(id, null)).toBeNull();
  });

  it('keeps runtime delivery and acquisition disabled even if a caller offers an unverified pin', () => {
    expect(preparation.preparation).toEqual({ state: 'private_review_pending', candidate_verified: true, acquisition_active: false,
      artwork_accepted: false, application_ids_agreed: true });
    expect(preparation.release.manifest_sha256).toBe('6e1f2cb2f67503c63e3ab8a27135b6f7579f894e0d62b814bfa89df3a45ae9e9');
    expect(activeLock.releases).toHaveLength(14);
    expect(activeLock.releases.some(({ family_id }) => family_id === GHOST_PLANT_FAMILY)).toBe(false);
    expect(support.pets.reduce((count, { potion_slugs }) => count + potion_slugs.length, 0)).toBe(31);
    const staged = stagedGhostPlantFixture(), sha = staged.manifestSha256;
    const pin = { family_id: GHOST_PLANT_FAMILY, release_version: '1.0.0', manifest_sha256: sha,
      directory: `${GHOST_PLANT_FAMILY}/1.0.0/${sha}` };
    const prefix = `../avatar/shared/${pin.directory}/`, manifests = { [`${prefix}manifest.json`]: staged.release };
    const urls = Object.fromEntries(staged.release.files.map(({ path }) => [`${prefix}${path}`, staged.resolveUrl(path)]));
    const indexes = { [`${prefix}manifest.json`]: staged.manifestUrl };
    expect(stagedElementalRelease(manifests, urls, { releases: [pin] }, indexes, GHOST_PLANT_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, urls, undefined, indexes, GHOST_PLANT_FAMILY)).toBeNull();
    for (const species of GHOST_PLANT_SPECIES) {
      expect(support.pets.find(({ species_slug }) => species_slug === species)?.potion_slugs).toEqual(['base']);
      for (const potion of ['fire', 'ice']) for (const stage of stages) {
        const creature = ghostPlantCreature(species, potion, stage);
        expect(resolveElementalAppearance(creature, 'pet')).toBeNull();
        expect(resolveAppearance(creature)).toBeNull();
        expect(resolveElementalPreviewAppearance(ghostPlantEgg(species), stage, creature.potion)).toBeNull();
        expect(resolveElementalPortrait(`${species}${suffix[stage]}`, potion)).toBeNull();
      }
    }
  });

  it.each(GHOST_PLANT_SPECIES)('retains natural %s eggs and readable forms across Base/Fire/Ice without granting ownership', (species) => {
    const forms = species === 'meshtint-ghost' ? [null, 'Ghost', 'Spook', 'Phantom'] : [null, 'Seed', 'Sprout', 'Flower Pot Monster'];
    for (const potion of ['base', 'fire', 'ice']) {
      expect(companionLifecycle({ slug: species, sprite_key: species }, { slug: potion }).map(({ form }) => form)).toEqual(forms);
    }
    const egg = ghostPlantEgg(species), staged = stagedGhostPlantFixture();
    expect(resolveElementalPreviewAppearance({ ...egg, slug: `${species}-fire-egg` }, 'baby', { slug: 'fire' }, staged)).toBeNull();
    expect(resolveElementalPreviewAppearance({ ...egg, metadata: { species: 'meshtint-bee' } }, 'baby', { slug: 'fire' }, staged)).toBeNull();
    expect(ownedAppearanceStages({ pets: [egg], mounts: [] }, { slug: species }, { slug: 'fire' })).toEqual([]);
  });

  it('permits only the separate explicit review pin while ordinary delivery stays unavailable', () => {
    expect(evaluationLock.releases).toHaveLength(1);
    const pin = evaluationLock.releases[0], staged = stagedGhostPlantFixture();
    expect(pin).toEqual({ ...preparation.release,
      directory: `${GHOST_PLANT_FAMILY}/1.0.0/${preparation.release.manifest_sha256}` });
    // Synthetic maps establish adapter routing only. The loopback server
    // separately verifies the actual immutable manifest and every payload.
    const prefix = `../avatar/shared/${pin.directory}/`, manifests = { [`${prefix}manifest.json`]: staged.release };
    const urls = Object.fromEntries(staged.release.files.map(({ path }) => [`${prefix}${path}`, staged.resolveUrl(path)]));
    const indexes = { [`${prefix}manifest.json`]: staged.manifestUrl };
    const explicit = stagedElementalRelease(manifests, urls, evaluationLock, indexes, GHOST_PLANT_FAMILY);
    expect(explicit?.release).toBe(staged.release);
    expect(stagedElementalRelease(manifests, urls, undefined, indexes, GHOST_PLANT_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, {}, evaluationLock, indexes, GHOST_PLANT_FAMILY)).toBeNull();
    expect(stagedElementalRelease(manifests, urls, evaluationLock, {}, GHOST_PLANT_FAMILY)).toBeNull();
    for (const [species, potion, stage] of appearances) {
      expect(resolveElementalAppearance(ghostPlantCreature(species, potion, stage), 'pet', explicit)?.key).toBe(`${species}-${potion}-${stage}`);
    }
  });

  it.each(preparation.families.flatMap(({ species_slug, challenges }) => challenges.map((challenge) => [species_slug, challenge])))(
    'withholds %s $catalog_icon Baby artwork until that exact appearance has hatched', (species, challenge) => {
    const goal = { name: challenge.name, catalog_icon: challenge.catalog_icon, origin: 'catalog', description: 'Complete the qualifying accomplishments.' };
    expect(isSurpriseChallenge(goal)).toBe(true);
    const visible = (stable) => challengeSurprise(goal, true, stable).hideArt;
    expect(visible(null)).toBe(true);
    expect(visible({ pets: [], mounts: [] })).toBe(true);
    expect(visible({ pets: [ghostPlantCreature(species, 'base')], mounts: [] })).toBe(true);
    expect(visible({ pets: [ghostPlantCreature(species, challenge.potion_slug === 'fire' ? 'ice' : 'fire')], mounts: [] })).toBe(true);
    expect(visible({ pets: [ghostPlantCreature(species === 'meshtint-ghost' ? 'meshtint-potted-plant' : 'meshtint-ghost', challenge.potion_slug)], mounts: [] })).toBe(true);
    expect(visible({ pets: [ghostPlantCreature(species, challenge.potion_slug)], mounts: [] })).toBe(false);
    expect(challengeSurprise(goal, false, null).hideArt).toBe(false);
    });

  it('fails for wrong identities, absent idle bindings, unsupported stages and missing exact model/portrait files', () => {
    const staged = stagedGhostPlantFixture(), species = 'meshtint-ghost', owned = ghostPlantCreature(species, 'fire');
    expect(resolveElementalAppearance({ ...owned, species: { slug: species, sprite_key: 'meshtint-potted-plant' } }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(ghostPlantCreature(species, 'base'), 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...owned, lifecycle_stage: 'egg' }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...owned, lifecycle_stage: 'grown' }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(owned, 'pet', stagedElementalFixture())).toBeNull();
    expect(resolveElementalAppearance(owned, 'pet', { ...staged, resolveUrl: () => null })).toBeNull();
    expect(resolveElementalPortrait(species, 'fire', { ...staged, resolveUrl: () => null })).toBeNull();
    staged.release.appearance_bindings.stages = staged.release.appearance_bindings.stages.filter((binding) => !(binding.species_slug === species
      && binding.potion_slug === 'fire' && binding.lifecycle_stage === 'baby' && binding.motion === 'idle'));
    expect(resolveElementalAppearance(owned, 'pet', staged)).toBeNull();
    expect(resolveElementalPortrait(species, 'fire', staged)).toBeNull();
    expect(resolveElementalCatalogIcon('source-rest-take', staged)).toBeNull();
  });
});
