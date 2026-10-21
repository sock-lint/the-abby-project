import { resolveCompanionAppearance, validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';
import expansion from '../../../shared/catalog/elemental-expansion.json';

const manifests = import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, import: 'default' });
const indexes = import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, query: '?url', import: 'default' });
const files = import.meta.glob('../avatar/shared/**/*.{glb,png}', { eager: true, query: '?url', import: 'default' });
export const ELEMENTAL_FAMILY = 'abby-elemental-companions';
export const ELEMENTAL_VERSION = '1.0.0';
export const ELEMENTAL_MANIFEST_SHA256 = 'fe271f2ef6909dec7cb6fb44dc70635bd7efbb9bf01a1f74052065fcce675048';
const STAGES = ['baby', 'middle', 'grown'];
const RELEASES = [{ family_id: ELEMENTAL_FAMILY, release_version: ELEMENTAL_VERSION, manifest_sha256: ELEMENTAL_MANIFEST_SHA256 }, expansion.release];
const FAMILIES = new Map([
  ['chick', { sprite_key: 'cute-chick', egg_item_slug: 'chick-egg', release_family_id: ELEMENTAL_FAMILY }],
  ['meshtint-wolf', { sprite_key: 'meshtint-wolf', egg_item_slug: 'meshtint-wolf-egg', release_family_id: ELEMENTAL_FAMILY }],
  ...expansion.families.map((family) => [family.species_slug, { ...family, release_family_id: expansion.release.family_id }]),
]);

export function elementalFamilyId(speciesSlug) {
  return FAMILIES.get(speciesSlug)?.release_family_id || null;
}

/** Each adopted family requires its own verified immutable pin. A preparation
 * descriptor with no digest cannot activate assets, even with an injected lock. */
export function stagedElementalRelease(available = manifests, urls = files, lock = assetLock, manifestUrls = indexes, familyId = ELEMENTAL_FAMILY) {
  const accepted = RELEASES.find((entry) => entry.family_id === familyId);
  const pin = lock.releases?.find((entry) => entry.family_id === familyId);
  if (!accepted?.manifest_sha256 || !pin || pin.release_version !== accepted.release_version || pin.manifest_sha256 !== accepted.manifest_sha256
    || pin.directory !== `${familyId}/${accepted.release_version}/${accepted.manifest_sha256}`) return null;
  const prefix = `../avatar/shared/${pin.directory}/`, release = available[`${prefix}manifest.json`];
  const manifestUrl = manifestUrls[`${prefix}manifest.json`];
  if (!release || !manifestUrl || release.family_id !== familyId || release.release_version !== accepted.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  if (release.appearance_bindings?.schema_version !== 1) return null;
  const resolveUrl = (path) => urls[`${prefix}${path}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { release, resolveUrl, manifestUrl, manifestSha256: pin.manifest_sha256 };
}

export function isElementalCompanion(species, potion) {
  return Boolean(FAMILIES.get(species?.slug)?.sprite_key === species?.sprite_key && species?.sprite_key && ['fire', 'ice'].includes(potion?.slug));
}

export function elementalEvolutionStages(creature) {
  return creature?.id && creature.species?.slug === 'chick' && isElementalCompanion(creature.species, creature.potion) ? STAGES : [];
}

export function elementalMotions(release, selection, resolveUrl) {
  return (release.appearance_bindings?.stages || []).filter((binding) => ['species_slug', 'potion_slug', 'lifecycle_stage']
    .every((key) => binding[key] === selection[key])).flatMap((binding) => {
    const resolved = resolveCompanionAppearance(release, { ...selection, motion: binding.motion });
    const clip = resolved.variant.animations.clips.find((entry) => entry.name === resolved.variant.animations.actions[binding.action]);
    const url = resolveUrl(resolved.variant.file);
    if (!clip || !url) return [];
    return [{ id: binding.variant_id, variantId: binding.variant_id, motion: binding.motion, action: binding.action,
      label: resolved.variant.label, clip: clip.name, loop: clip.loop, nativeLoop: clip.loop,
      rootMotion: clip.root_motion, duration: clip.duration, bounds: clip.bounds, url }];
  });
}

function appearanceFor(species, potion, stage, staged) {
  const familyId = elementalFamilyId(species?.slug);
  if (!staged || !isElementalCompanion(species, potion) || !STAGES.includes(stage) || staged.release.family_id !== familyId) return null;
  const selection = { family_id: familyId, species_slug: species.slug, potion_slug: potion.slug, lifecycle_stage: stage };
  try {
    const idle = resolveCompanionAppearance(staged.release, { ...selection, motion: 'idle' });
    const url = staged.resolveUrl(idle.variant.file);
    if (!url) return null;
    const motions = elementalMotions(staged.release, selection, staged.resolveUrl);
    const play = ['fly-forward-in-place', 'walk-forward-in-place', 'run-forward-in-place', 'jump-forward-in-place', 'jump-in-place']
      .map((motion) => motions.find((entry) => entry.motion === motion)).find(Boolean);
    const interactions = Object.fromEntries([['play', play], ['left', motions.find((entry) => entry.motion === 'turn-left')],
      ['right', motions.find((entry) => entry.motion === 'turn-right')]].filter(([, motion]) => motion));
    // Bird's static parent preserves relative Chick/Fledgling/Bird sizes.
    // Other families retain the roster's static per-stage idle framing.
    const reference = species.slug === 'chick'
      ? resolveCompanionAppearance(staged.release, { ...selection, lifecycle_stage: 'grown', motion: 'idle' }) : idle;
    const referenceClip = reference.variant.animations.clips.find((entry) => entry.name === reference.variant.animations.actions[reference.action]);
    return { ...staged, pipeline: 'abby-assets-elemental', key: idle.asset.id, assetId: idle.asset.id, stage, selection,
      speciesSlug: species.slug, potionSlug: potion.slug, defaultVariantId: idle.variant.id, defaultAction: idle.action,
      idleClip: idle.variant.animations.actions[idle.action], url, rotationY: 0, motions, interactions,
      referenceBounds: species.slug === 'chick' ? reference.variant.bounds : referenceClip?.bounds || reference.variant.bounds, framing: species.slug === 'chick' ? 'bird' : 'roster',
      playLabel: play?.motion.startsWith('fly') ? 'Fly together' : play?.motion.startsWith('walk') || play?.motion.startsWith('run') ? 'Walk together' : 'Hop together' };
  } catch { return null; }
}

export function resolveElementalAppearance(creature, kind = 'pet', staged) {
  if (!creature?.id) return null;
  const installed = staged === undefined ? stagedElementalRelease(undefined, undefined, undefined, undefined, elementalFamilyId(creature.species?.slug)) : staged;
  const stage = kind === 'mount' || creature.evolved_to_mount === true ? 'grown'
    : ['baby', 'middle'].includes(creature.lifecycle_stage) ? creature.lifecycle_stage : null;
  return appearanceFor(creature.species, creature.potion, stage, installed);
}

/** Inventory previews select local presentation only. Retained typed egg
 * identities are required; previewing a stage never establishes ownership. */
export function resolveElementalPreviewAppearance(item, stage, potion, staged) {
  const family = FAMILIES.get(item?.pet_species_slug);
  if (item?.item_type !== 'egg' || !family || item.slug !== family.egg_item_slug || item.metadata?.species !== item.pet_species_slug) return null;
  const species = { slug: item.pet_species_slug, sprite_key: family.sprite_key };
  const installed = staged === undefined ? stagedElementalRelease(undefined, undefined, undefined, undefined, family.release_family_id) : staged;
  return appearanceFor(species, potion, stage, installed);
}
