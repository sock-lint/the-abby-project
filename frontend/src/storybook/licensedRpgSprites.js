import presentation from './presentation.json';
import { resolveSupplementalPortrait } from '../companion/supplementalPortraits';

// Optional imports keep public builds usable without the private staging folder.
// The stage script copies these portraits and their matching overlay together.
const manifests = import.meta.glob('./licensed/presentation.json', { eager: true, import: 'default' });
const assets = import.meta.glob('./licensed/*.png', { eager: true, query: '?url', import: 'default' });
const art = (name) => assets[`./licensed/${name}`];
const PORTRAITS = new Map([
  ['cute-chick', 'chick.png'],
  ['cute-chick-fledgling', 'fledgling.png'],
  ['cute-chick-mount', 'bird.png'],
]);

// These explicit keys belong to the server's Chick species. Generic Meadow
// preview art must never be reassigned to a different owned species.
export function resolveLicensedRpgSprite(spriteKey, manifest, resolveArt) {
  const portrait = PORTRAITS.get(spriteKey);
  const companion = manifest?.companion;
  if (!portrait
    || manifest?.schema_version !== presentation.schema_version
    || companion?.id !== presentation.companion.id
    || companion?.art_key !== 'chick'
    || companion?.temporary !== false
    || companion?.portrait !== 'chick.png'
    || !resolveArt?.('chick.png')) return null;

  const url = resolveArt(portrait);
  return url ? { url, frames: 1 } : null;
}

export function getLicensedRpgSprite(spriteKey, variantId = 'icon') {
  return resolveSupplementalPortrait(spriteKey, variantId) || resolveLicensedRpgSprite(spriteKey, manifests['./licensed/presentation.json'], art);
}
