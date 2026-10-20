import { stagedElementalRelease } from './sharedElementalRelease';

const PORTRAIT_KEYS = new Map([
  ['cute-chick', ['chick', 'baby']],
  ['cute-chick-fledgling', ['chick', 'middle']],
  ['cute-chick-mount', ['chick', 'grown']],
  ['meshtint-wolf', ['meshtint-wolf', 'baby']],
  ['meshtint-wolf-middle', ['meshtint-wolf', 'middle']],
  ['meshtint-wolf-mount', ['meshtint-wolf', 'grown']],
]);
const UI_IMAGES = new Set([
  'item-fire-potion', 'item-ice-potion',
  'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail',
]);
let installed;
const installedElemental = () => installed === undefined ? (installed = stagedElementalRelease()) : installed;

function portrait(staged, assetId, variantId) {
  const asset = staged?.release.assets.find((entry) => entry.id === assetId && entry.kind === 'image');
  const variant = asset?.variants.find((entry) => entry.id === variantId && entry.animations == null);
  const file = variant && staged.release.files.find((entry) => entry.path === variant.file);
  if (file?.media_type !== 'image/png' || !/^objects\/[a-f0-9]{64}\.png$/.test(file.path)) return null;
  const url = staged.resolveUrl(file.path);
  return url ? { url, frames: 1, label: asset.label } : null;
}

function appearanceBinding(staged, speciesSlug, potionSlug, stage) {
  if (!['fire', 'ice'].includes(potionSlug)) return null;
  return staged?.release.appearance_bindings?.stages?.find((binding) => binding.species_slug === speciesSlug
    && binding.potion_slug === potionSlug && binding.lifecycle_stage === stage && binding.motion === 'idle') || null;
}

/** These appearances declare only a 256px icon. Use that exact portrait at
 * every CSS size, independently of the source-* native motion variants. */
export function resolveElementalPortrait(spriteKey, potionSlug, staged = installedElemental()) {
  const [speciesSlug, stage] = PORTRAIT_KEYS.get(spriteKey) || [];
  if (!speciesSlug) return null;
  const binding = appearanceBinding(staged, speciesSlug, potionSlug, stage);
  return binding ? portrait(staged, binding.portrait_asset_id, binding.portrait_variant_id) : null;
}

/** Django supplies typed potion/challenge image IDs. A native model ID or
 * an undeclared image cannot select catalog artwork from this release. */
export function resolveElementalCatalogIcon(assetId, staged = installedElemental()) {
  if (!assetId || !staged) return null;
  if (UI_IMAGES.has(assetId)) return portrait(staged, assetId, 'icon');
  for (const [speciesSlug, stage] of PORTRAIT_KEYS.values()) {
    for (const potionSlug of ['fire', 'ice']) {
      const binding = appearanceBinding(staged, speciesSlug, potionSlug, stage);
      if (binding?.portrait_asset_id === assetId) return portrait(staged, assetId, binding.portrait_variant_id);
    }
  }
  return null;
}
