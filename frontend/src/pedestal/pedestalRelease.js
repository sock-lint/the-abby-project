import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';

const manifests = import.meta.glob('../avatar/shared/meshtint-pedestal-card-ui/**/manifest.json', { eager: true, import: 'default' });
const manifestUrls = import.meta.glob('../avatar/shared/meshtint-pedestal-card-ui/**/manifest.json', { eager: true, query: '?url', import: 'default' });
const files = import.meta.glob('../avatar/shared/meshtint-pedestal-card-ui/**/*.{glb,png}', { eager: true, query: '?url', import: 'default' });

export const PEDESTAL_FAMILY = 'meshtint-pedestal-card-ui';
export { PEDESTAL_EGG_ASSETS as PEDESTAL_EGG_IDS } from './pedestal.constants';
export const PEDESTAL_IMAGE_IDS = [
  'card-back-01', 'card-front-chance', 'card-front-darkness', 'card-front-egg-star',
  'card-front-electric', 'card-front-fire', 'card-front-gem', 'card-front-ice',
  'card-front-legendary', 'card-front-light', 'card-front-melee', 'card-front-nature',
  'card-front-treasure', 'card-front-wind', 'corner-decor-01', 'frame-gold',
  'portrait-legendary-evolution-egg', 'star-lit', 'star-unlit',
];

/** Build-time import verifies the immutable manifest and every payload. Runtime
 * model loading rechecks its digest. Missing private inputs leave DOM fallbacks. */
export function stagedPedestalRelease(available = manifests, urls = files, lock = assetLock, indexes = manifestUrls) {
  const pin = lock.releases?.find((entry) => entry.family_id === PEDESTAL_FAMILY);
  if (!pin) return null;
  const prefix = `../avatar/shared/${pin.directory}/`;
  const release = available[`${prefix}manifest.json`];
  const manifestUrl = indexes[`${prefix}manifest.json`];
  if (!release || !manifestUrl || release.family_id !== pin.family_id || release.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  const resolveUrl = (file) => urls[`${prefix}${file}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { release, resolveUrl, manifestUrl, manifestSha256: pin.manifest_sha256 };
}

/** Artwork selection is presentation only. No inventory, rarity or pet binding
 * is inferred from these IDs. Image-kind assets never enter the GLB loader. */
export function resolvePedestalImage(assetId, variantId = 'web', staged = stagedPedestalRelease()) {
  if (!PEDESTAL_IMAGE_IDS.includes(assetId) || !staged || !['web', 'native'].includes(variantId)) return null;
  const asset = staged.release.assets.find((entry) => entry.id === assetId && entry.kind === 'image');
  const variant = asset?.variants.find((entry) => entry.id === variantId)
    || (variantId === 'native' && asset?.variants.find((entry) => entry.id === 'web'));
  if (!variant) return null;
  const file = staged.release.files.find((entry) => entry.path === variant.file && entry.media_type === 'image/png');
  const url = file && staged.resolveUrl(file.path);
  if (!url) return null;
  const size = variant.id === 'native' ? 1024 : 512;
  return { url, width: size, height: size, assetId, variantId: variant.id };
}
