// These seven exact, verified images are supplemental delivery files rather
// than invented asset IDs in the retained Bird/catalog release manifests.
const images = import.meta.glob('./supplemental/*.png', { eager: true, query: '?url', import: 'default' });
const names = {
  'cute-chick': 'chick',
  'cute-chick-fledgling': 'fledgling',
  'cute-chick-mount': 'bird',
  'chick-egg': 'normal-egg',
  'normal-egg': 'normal-egg',
};

export function resolveSupplementalPortrait(spriteKey, variantId = 'icon', urls = images) {
  const name = names[spriteKey];
  if (!name || !['icon', 'native'].includes(variantId)) return null;
  const native = variantId === 'native' && name !== 'normal-egg' ? '-native' : '';
  const url = urls[`./supplemental/${name}${native}.png`];
  return url ? { url, frames: 1 } : null;
}

// Existing server-verified catalog IDs retain their identity. Their supplied
// supplemental image does not become a fabricated asset in another release.
export function resolveSupplementalCatalogIcon(assetId, urls = images) {
  const sprite = { 'item-chick-egg': 'chick-egg', 'portrait-chick': 'cute-chick', 'portrait-chick-grown': 'cute-chick-mount' }[assetId];
  return sprite ? resolveSupplementalPortrait(sprite, 'icon', urls) : null;
}
