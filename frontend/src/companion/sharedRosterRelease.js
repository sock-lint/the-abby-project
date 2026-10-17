import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';
import roster from '../../../shared/catalog/companion-roster.json';

const manifests = import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, import: 'default' });
const indexes = import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, query: '?url', import: 'default' });
const files = import.meta.glob('../avatar/shared/**/*.{glb,png}', { eager: true, query: '?url', import: 'default' });
export const ROSTER_FAMILY = 'meshtint-companion-roster';

export function stagedRosterRelease(available = manifests, urls = files, lock = assetLock, manifestUrls = indexes) {
  const pin = lock.releases?.find((entry) => entry.family_id === ROSTER_FAMILY);
  if (!pin || pin.manifest_sha256 !== roster.release.manifest_sha256 || pin.directory !== roster.release.directory) return null;
  const prefix = `../avatar/shared/${pin.directory}/`, release = available[`${prefix}manifest.json`];
  const manifestUrl = manifestUrls[`${prefix}manifest.json`];
  if (!release || !manifestUrl || release.family_id !== ROSTER_FAMILY || release.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  const resolveUrl = (path) => urls[`${prefix}${path}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { release, resolveUrl, manifestUrl, manifestSha256: pin.manifest_sha256 };
}
let installed;
const installedRoster = () => installed === undefined ? (installed = stagedRosterRelease()) : installed;

export function rosterFamily(species, potion) {
  return roster.families.find((family) => family.species_slug === species?.slug && family.sprite_key === species?.sprite_key
    && family.potion_slugs.includes(potion?.slug)) || null;
}

export function rosterEggFamily(item) {
  if (item?.item_type !== 'egg') return null;
  return roster.families.find((family) => item.slug === family.egg.item_slug && item.pet_species_slug === family.species_slug
    && item.metadata?.species === family.species_slug) || null;
}

// A multi-action egg has a unique control per clip; a native creature take
// retains its own complete variant/rig. Alias actions sharing a clip appear once.
export function rosterMotions(release, assetId, resolveUrl) {
  const asset = release.assets.find((entry) => entry.id === assetId && entry.kind !== 'image');
  return (asset?.variants || []).flatMap((variant) => (variant.animations?.clips || []).flatMap((clip) => {
    const actions = Object.entries(variant.animations.actions).filter(([, name]) => name === clip.name);
    const action = actions.find(([name]) => name === 'idle')?.[0] || actions[0]?.[0];
    const url = resolveUrl(variant.file);
    if (!action || !url || !variant.file.endsWith('.glb')) return [];
    const boundedTravel = asset.kind === 'prop' && action === 'roll-forward-w-root';
    return [{ id: variant.animations.clips.length === 1 ? variant.id : `${variant.id}:${action}`,
      variantId: variant.id, action, clip: clip.name, label: `${clip.name}${boundedTravel ? ' (once)' : ''}`, url,
      loop: boundedTravel ? false : clip.loop, nativeLoop: clip.loop,
      rootMotion: clip.root_motion, duration: clip.duration, bounds: clip.bounds }];
  }));
}

function appearanceFor(family, stage, staged) {
  if (!staged) return null;
  const binding = stage === 'egg' ? family.egg : family.stages[stage];
  if (!binding) return null;
  const asset = staged.release.assets.find((entry) => entry.id === binding.asset_id && entry.kind !== 'image');
  const variantId = binding.default_variant_id || binding.variant_id;
  const variant = asset?.variants.find((entry) => entry.id === variantId);
  const defaultAction = binding.default_action || 'idle';
  const idleClip = variant?.animations?.actions?.[defaultAction], url = variant && staged.resolveUrl(variant.file);
  if (!idleClip || !url || !variant.file.endsWith('.glb')) return null;
  const motions = rosterMotions(staged.release, binding.asset_id, staged.resolveUrl);
  const play = ['fly-forward-in-place', 'walk-forward-in-place', 'run-forward-in-place', 'jump-forward-in-place', 'bounce', 'shake'].map((action) => motions.find((motion) => motion.action === action)).find(Boolean);
  const interactions = Object.fromEntries([['play', play], ['left', motions.find((motion) => motion.action === 'turn-left')], ['right', motions.find((motion) => motion.action === 'turn-right')]].filter(([, motion]) => motion));
  // Normalize each stage's view once from its native idle. All takes retain
  // that parent scale; neither mesh geometry nor animation keys are rewritten.
  const referenceBounds = variant.animations.clips.find((clip) => clip.name === idleClip)?.bounds || variant.bounds;
  return { ...staged, pipeline: 'abby-assets-roster', key: binding.asset_id, assetId: binding.asset_id, stage,
    defaultVariantId: variantId, defaultAction, idleClip, url, rotationY: 0, motions, interactions, referenceBounds,
    playLabel: play?.action.startsWith('fly') ? 'Fly together' : play?.action.startsWith('walk') || play?.action.startsWith('run') ? 'Walk together' : play?.action.startsWith('jump') || play?.action === 'bounce' ? 'Hop together' : 'Play together' };
}

export function resolveRosterAppearance(creature, kind = 'pet', staged = installedRoster()) {
  const family = rosterFamily(creature?.species, creature?.potion);
  if (!creature?.id || !family) return null;
  const stage = kind === 'mount' || creature.evolved_to_mount === true ? 'grown'
    : ['baby', 'middle'].includes(creature.lifecycle_stage) ? creature.lifecycle_stage : null;
  return stage ? appearanceFor(family, stage, staged) : null;
}

export function resolveRosterEggAppearance(item, staged = installedRoster()) {
  const family = rosterEggFamily(item);
  return family ? appearanceFor(family, 'egg', staged) : null;
}

export function resolveRosterPreviewAppearance(item, stage, staged = installedRoster()) {
  const family = rosterEggFamily(item);
  return family && ['egg', 'baby', 'middle', 'grown'].includes(stage) ? appearanceFor(family, stage, staged) : null;
}

function portrait(staged, assetId, variantId) {
  const asset = staged?.release.assets.find((entry) => entry.id === assetId && entry.kind === 'image');
  const variant = asset?.variants.find((entry) => entry.id === variantId), url = variant && staged.resolveUrl(variant.file);
  return url && variant.file.endsWith('.png') ? { url, frames: 1 } : null;
}

export function resolveRosterPortrait(spriteKey, potionSlug = 'base', variantId = 'icon', staged = installedRoster()) {
  if (potionSlug && potionSlug !== 'base') return null;
  for (const family of roster.families) {
    const stage = spriteKey === family.sprite_key ? 'baby' : spriteKey === `${family.sprite_key}-middle` ? 'middle' : spriteKey === `${family.sprite_key}-mount` ? 'grown' : null;
    if (stage) return portrait(staged, family.stages[stage].portrait_asset_id, variantId);
  }
  return null;
}

export function resolveRosterEggPortrait(item, staged = installedRoster()) {
  const family = rosterEggFamily(item);
  return family ? portrait(staged, family.egg.portrait_asset_id, family.egg.portrait_variant_id) : null;
}

// These image IDs are returned by Django only after its typed catalog binding
// check. A model ID, Dummy or an arbitrary image in the pack is never admitted.
export function resolveRosterCatalogIcon(assetId, staged = installedRoster()) {
  const accepted = roster.families.some((family) => family.egg.portrait_asset_id === assetId
    || Object.values(family.stages).some((stage) => stage.portrait_asset_id === assetId));
  return accepted ? portrait(staged, assetId, 'icon') : null;
}
