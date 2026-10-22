import { describe, expect, it } from 'vitest';
import { resolveCompanionAppearance, validateAssetPackManifest } from '@abby-assets/contracts';
import { resolveAppearance } from './appearance';
import { elementalMotions, ELEMENTAL_FAMILY, ELEMENTAL_MANIFEST_SHA256, elementalEvolutionStages,
  isElementalCompanion, resolveElementalAppearance, resolveElementalPreviewAppearance, stagedElementalRelease } from './sharedElementalRelease';
import { stagedElementalFixture, syntheticElemental } from '../test/elementalReleaseFixture';
import { stagedBirdFixture, syntheticBird } from '../test/birdReleaseFixture';
import { rosterFixture, rosterPet } from '../test/rosterReleaseFixture';
import expansion from '../../../shared/catalog/elemental-expansion.json';

const combinations = ['chick', 'meshtint-wolf'].flatMap((species) => ['fire', 'ice'].flatMap((potion) => ['baby', 'middle', 'grown'].map((stage) => [species, potion, stage])));

describe('Exact elemental appearance bindings', () => {
  it.each(['fire', 'ice'])('gives Dragon middle %s logical idle aliases distinct controls without inventing native variants', (potion) => {
    const staged = stagedElementalFixture(true);
    expect(validateAssetPackManifest(staged.release)).toBe(staged.release);
    const appearance = resolveElementalAppearance(syntheticElemental('meshtint-dragon', potion, 'middle'), 'pet', staged);
    const idle = appearance.motions.find((entry) => entry.motion === 'idle');
    const flying = appearance.motions.find((entry) => entry.motion === 'fly-idle');
    expect(idle.id).toBe('idle');
    expect(flying.id).toBe('fly-idle');
    expect(new Set(appearance.motions.map((entry) => entry.id)).size).toBe(appearance.motions.length);
    expect(idle.variantId).toBe('source-fly-idle');
    expect(flying.variantId).toBe(idle.variantId);
    expect(flying.url).toBe(idle.url);
    expect(flying.clip).toBe(idle.clip);
    expect(staged.release.assets.find((entry) => entry.id === appearance.assetId).variants.some((variant) => variant.id === 'source-idle')).toBe(false);
  });

  it('resolves Dragon and Mushroom exact stage bindings only from their own staged release', () => {
    const staged = stagedElementalFixture(true);
    expect(validateAssetPackManifest(staged.release)).toBe(staged.release);
    for (const species of ['meshtint-dragon', 'meshtint-mushroom']) {
      for (const potion of ['fire', 'ice']) for (const stage of ['baby', 'middle', 'grown']) {
        const creature = syntheticElemental(species, potion, stage);
        const appearance = resolveElementalAppearance(creature, 'pet', staged);
        expect(appearance.selection.family_id).toBe('abby-elemental-dragon-mushroom');
        expect(appearance.key).toBe(`${species}-${potion}-${stage}`);
        expect(appearance.defaultVariantId).toBe(species === 'meshtint-dragon' && stage === 'middle' ? 'source-fly-idle' : 'source-idle');
        expect(appearance.defaultAction).toBe('idle');
        const egg = { item_type: 'egg', slug: `${species}-egg`, pet_species_slug: species, metadata: { species } };
        expect(resolveElementalPreviewAppearance(egg, stage, { slug: potion }, staged).key).toBe(appearance.key);
        expect(resolveElementalAppearance(creature, 'pet', null)).toBeNull();
        expect(resolveElementalAppearance(creature, 'pet', stagedElementalFixture())).toBeNull();
      }
    }
    expect(resolveElementalAppearance(syntheticElemental(), 'pet', staged)).toBeNull();
  });

  it('accepts only the adopted expansion digest with its complete immutable directory', () => {
    const { release } = stagedElementalFixture(true), sha = expansion.release.manifest_sha256;
    expect(sha).toMatch(/^[a-f0-9]{64}$/);
    const pin = { family_id: release.family_id, release_version: '1.0.0', manifest_sha256: sha,
      directory: `${release.family_id}/1.0.0/${sha}` };
    const prefix = `../avatar/shared/${pin.directory}/`;
    const manifests = { [`${prefix}manifest.json`]: release };
    const urls = Object.fromEntries(release.files.map(({ path }) => [`${prefix}${path}`, `/synthetic/${path}`]));
    const indexes = { [`${prefix}manifest.json`]: '/synthetic/manifest.json' };
    expect(stagedElementalRelease(manifests, urls, { releases: [pin] }, indexes, release.family_id).release).toBe(release);
    expect(stagedElementalRelease(manifests, urls, { releases: [{ ...pin, manifest_sha256: 'a'.repeat(64) }] }, indexes, release.family_id)).toBeNull();
    expect(stagedElementalRelease(manifests, urls, { releases: [{ ...pin, directory: `${release.family_id}/1.0.0/${'a'.repeat(64)}` }] }, indexes, release.family_id)).toBeNull();
  });

  it('keeps every native motion binding distinct from the selected potion across all twelve appearances', () => {
    const staged = stagedElementalFixture();
    expect(validateAssetPackManifest(staged.release)).toBe(staged.release);
    const motions = combinations.flatMap(([species, potion, stage]) => {
      const appearance = resolveElementalAppearance(syntheticElemental(species, potion, stage), 'pet', staged);
      expect(appearance.key).toBe(`${species}-${potion}-${stage}`);
      expect(appearance.selection.potion_slug).toBe(potion);
      expect(appearance.defaultVariantId).toBe('source-idle');
      expect(appearance.interactions.left.motion).toBe('turn-left');
      for (const motion of appearance.motions) {
        const resolved = resolveCompanionAppearance(staged.release, { ...appearance.selection, motion: motion.motion });
        expect(motion.variantId).toBe(resolved.variant.id);
        expect(motion.id).toBe(motion.motion);
        expect(motion.action).toBe(resolved.action);
        expect(motion.clip).toBe(resolved.variant.animations.actions[resolved.action]);
        expect(motion.url).toBe(staged.resolveUrl(resolved.variant.file));
      }
      return appearance.motions;
    });
    expect(motions).toHaveLength(178);
    expect(motions.filter((entry) => entry.rootMotion === 'source')).toHaveLength(178);
  });

  it.each(combinations)('uses the server-confirmed stage for %s %s %s', (species, potion, stage) => {
    const creature = syntheticElemental(species, potion, stage), staged = stagedElementalFixture();
    expect(resolveElementalAppearance(creature, 'pet', staged).stage).toBe(stage);
    expect(resolveElementalAppearance({ ...creature, growth_points: 100 }, 'pet', staged).stage).toBe(stage);
    expect(resolveElementalAppearance({ ...creature, lifecycle_stage: 'grown', evolved_to_mount: false }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...creature, lifecycle_stage: undefined, evolved_to_mount: false }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...creature, id: null }, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance(creature, 'mount', staged).stage).toBe('grown');
  });

  it('never broadens the existing Base Bird or roster adapters', () => {
    const staged = stagedElementalFixture();
    expect(resolveAppearance(syntheticElemental(), 'pet', undefined, undefined, null, null, staged).pipeline).toBe('abby-assets-elemental');
    expect(resolveAppearance(syntheticBird, 'pet', undefined, undefined, stagedBirdFixture(), null, staged).pipeline).toBe('abby-assets-bird');
    expect(resolveAppearance(rosterPet(), 'pet', undefined, undefined, null, rosterFixture(), staged).pipeline).toBe('abby-assets-roster');
    expect(resolveElementalAppearance(syntheticBird, 'pet', staged)).toBeNull();
    expect(resolveElementalAppearance({ ...syntheticElemental(), species: { slug: 'chick', sprite_key: 'wolf' } }, 'pet', staged)).toBeNull();
    expect(isElementalCompanion({ slug: 'fox', sprite_key: 'cute-chick' }, { slug: 'fire' })).toBe(false);
    expect(elementalEvolutionStages(syntheticElemental())).toEqual(['baby', 'middle', 'grown']);
    expect(elementalEvolutionStages(syntheticElemental('meshtint-wolf'))).toEqual([]);
    expect(resolveElementalAppearance(syntheticElemental(), 'pet', null)).toBeNull();
  });

  it('keeps the Bird relative-stage frame and Wolf per-stage frame independent from moving takes', () => {
    const staged = stagedElementalFixture();
    const grownAsset = staged.release.assets.find((entry) => entry.id === 'chick-fire-grown');
    const grownIdle = grownAsset.variants.find((entry) => entry.id === 'source-idle');
    grownIdle.animations.clips[0].bounds = { min: [-4, 1, -3], max: [4, 9, 3] };
    const [baby, middle, grown] = ['baby', 'middle', 'grown'].map((stage) => resolveElementalAppearance(syntheticElemental('chick', 'fire', stage), 'pet', staged));
    expect(baby.framing).toBe('bird');
    expect(baby.referenceBounds).toEqual(grownIdle.bounds);
    expect(baby.referenceBounds).not.toEqual(grownIdle.animations.clips[0].bounds);
    expect(baby.referenceBounds).toEqual(grown.referenceBounds);
    expect(middle.referenceBounds).toEqual(grown.referenceBounds);
    expect(grown.playLabel).toBe('Fly together');
    expect(middle.playLabel).toBe('Walk together');
    const wolf = resolveElementalAppearance(syntheticElemental('meshtint-wolf'), 'pet', staged);
    expect(wolf.framing).toBe('roster');
    expect(wolf.referenceBounds.max[1]).toBe(0.75);
  });

  it('previews only typed retained eggs with the explicitly chosen appearance and never a new egg identity', () => {
    const staged = stagedElementalFixture();
    for (const species of ['chick', 'meshtint-wolf']) {
      const egg = { slug: `${species}-egg`, item_type: 'egg', pet_species_slug: species, metadata: { species } };
      for (const potion of ['fire', 'ice']) for (const stage of ['baby', 'middle', 'grown']) {
        expect(resolveElementalPreviewAppearance(egg, stage, { slug: potion }, staged).key).toBe(`${species}-${potion}-${stage}`);
      }
      expect(resolveElementalPreviewAppearance({ ...egg, item_type: 'potion' }, 'baby', { slug: 'fire' }, staged)).toBeNull();
      expect(resolveElementalPreviewAppearance({ ...egg, metadata: { species: 'other' } }, 'baby', { slug: 'fire' }, staged)).toBeNull();
      expect(resolveElementalPreviewAppearance(egg, 'egg', { slug: 'fire' }, staged)).toBeNull();
      expect(resolveElementalPreviewAppearance(egg, 'baby', { slug: 'base' }, staged)).toBeNull();
    }
  });

  it('requires the exact immutable pin, schema, complete inventory and manifest URL', () => {
    const { release } = stagedElementalFixture();
    const pin = { family_id: ELEMENTAL_FAMILY, release_version: '1.0.0', manifest_sha256: ELEMENTAL_MANIFEST_SHA256,
      directory: `${ELEMENTAL_FAMILY}/1.0.0/${ELEMENTAL_MANIFEST_SHA256}` };
    const prefix = `../avatar/shared/${pin.directory}/`, available = { [`${prefix}manifest.json`]: release };
    const urls = Object.fromEntries(release.files.map((file) => [`${prefix}${file.path}`, `/test/${file.path}`]));
    const indexes = { [`${prefix}manifest.json`]: '/test/manifest.json' };
    expect(stagedElementalRelease(available, urls, { releases: [pin] }, indexes).release).toBe(release);
    expect(stagedElementalRelease(available, urls, { releases: [] }, indexes)).toBeNull();
    for (const field of ['manifest_sha256', 'release_version', 'directory']) {
      expect(stagedElementalRelease(available, urls, { releases: [{ ...pin, [field]: 'wrong' }] }, indexes)).toBeNull();
    }
    expect(stagedElementalRelease(available, urls, { releases: [pin] }, {})).toBeNull();
    expect(stagedElementalRelease({ [`${prefix}manifest.json`]: { ...release, appearance_bindings: null } }, urls, { releases: [pin] }, indexes)).toBeNull();
    expect(stagedElementalRelease({}, urls, { releases: [pin] }, indexes)).toBeNull();
    delete urls[Object.keys(urls)[0]];
    expect(stagedElementalRelease(available, urls, { releases: [pin] }, indexes)).toBeNull();
  });

  it.each([['chick', false], ['meshtint-dragon', true], ['meshtint-mushroom', true]])('fails closed for %s missing exact bindings or model URLs without a Base substitution', (species, expansion) => {
    const staged = stagedElementalFixture(expansion);
    staged.release.appearance_bindings.stages = staged.release.appearance_bindings.stages.filter((entry) => !(entry.species_slug === species && entry.potion_slug === 'fire' && entry.lifecycle_stage === 'baby'));
    expect(resolveElementalAppearance(syntheticElemental(species), 'pet', staged)).toBeNull();
    const absent = { ...stagedElementalFixture(expansion), resolveUrl: () => null };
    expect(resolveElementalAppearance(syntheticElemental(species), 'pet', absent)).toBeNull();
    expect(elementalMotions(staged.release, { family_id: ELEMENTAL_FAMILY, species_slug: 'unknown', potion_slug: 'fire', lifecycle_stage: 'baby' }, () => '/test')).toEqual([]);
  });
});
