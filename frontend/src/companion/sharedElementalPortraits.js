import { ELEMENTAL_FAMILY, elementalFamilyId, stagedElementalRelease } from './sharedElementalRelease';
import expansion from '../../../shared/catalog/elemental-expansion.json';

const PORTRAIT_KEYS = new Map([
  ['cute-chick', ['chick', 'baby']],
  ['cute-chick-fledgling', ['chick', 'middle']],
  ['cute-chick-mount', ['chick', 'grown']],
  ['meshtint-wolf', ['meshtint-wolf', 'baby']],
  ['meshtint-wolf-middle', ['meshtint-wolf', 'middle']],
  ['meshtint-wolf-mount', ['meshtint-wolf', 'grown']],
  ...expansion.families.flatMap(({ sprite_key, species_slug }) => [
    [sprite_key, [species_slug, 'baby']], [`${sprite_key}-middle`, [species_slug, 'middle']], [`${sprite_key}-mount`, [species_slug, 'grown']],
  ]),
]);
const UI_IMAGES = new Map([
  ...[
  'item-fire-potion', 'item-ice-potion',
  'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail',
  ].map((id) => [id, ELEMENTAL_FAMILY]),
  ...expansion.families.flatMap(({ challenges }) => challenges.map(({ catalog_icon }) => [catalog_icon, expansion.release.family_id])),
]);
const installed = new Map();
function stagedFamily(familyId, staged) {
  if (staged === undefined) {
    if (!installed.has(familyId)) installed.set(familyId, stagedElementalRelease(undefined, undefined, undefined, undefined, familyId));
    staged = installed.get(familyId);
  }
  return staged?.release.family_id === familyId ? staged : null;
}

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
export function resolveElementalPortrait(spriteKey, potionSlug, staged) {
  const [speciesSlug, stage] = PORTRAIT_KEYS.get(spriteKey) || [];
  if (!speciesSlug) return null;
  const selected = stagedFamily(elementalFamilyId(speciesSlug), staged);
  const binding = appearanceBinding(selected, speciesSlug, potionSlug, stage);
  return binding ? portrait(selected, binding.portrait_asset_id, binding.portrait_variant_id) : null;
}

/** Django supplies typed potion/challenge image IDs. A native model ID or
 * an undeclared image cannot select catalog artwork from this release. */
export function resolveElementalCatalogIcon(assetId, staged) {
  if (!assetId) return null;
  if (UI_IMAGES.has(assetId)) return portrait(stagedFamily(UI_IMAGES.get(assetId), staged), assetId, 'icon');
  for (const [speciesSlug, stage] of PORTRAIT_KEYS.values()) {
    const selected = stagedFamily(elementalFamilyId(speciesSlug), staged);
    for (const potionSlug of ['fire', 'ice']) {
      const binding = appearanceBinding(selected, speciesSlug, potionSlug, stage);
      if (binding?.portrait_asset_id === assetId) return portrait(selected, assetId, binding.portrait_variant_id);
    }
  }
  return null;
}
