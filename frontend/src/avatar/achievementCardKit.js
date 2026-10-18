import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';

const manifests = import.meta.glob('./shared/abby-achievement-card-kit/**/manifest.json', { eager: true, import: 'default' });
const manifestUrls = import.meta.glob('./shared/abby-achievement-card-kit/**/manifest.json', { eager: true, query: '?url', import: 'default' });
const files = import.meta.glob('./shared/abby-achievement-card-kit/**/*.png', { eager: true, query: '?url', import: 'default' });

export const ACHIEVEMENT_CARD_FAMILY = 'abby-achievement-card-kit';

// These are canvas geometry, not catalog bindings or earning rules. A card's
// width sets the scale for its corner slices and content inset together.
export const ACHIEVEMENT_CARD_IMAGES = Object.freeze({
  'abby-card-base-wide': { variantId: 'wide', width: 1024, height: 512, resizeInset: 64, contentInset: 96 },
  'abby-card-base-tall': { variantId: 'tall', width: 1024, height: 1280, resizeInset: 64, contentInset: 96 },
  'abby-card-border-gold-wide': { variantId: 'wide', width: 1024, height: 512, resizeInset: 64, contentInset: 96 },
  'abby-card-border-gold-tall': { variantId: 'tall', width: 1024, height: 1280, resizeInset: 64, contentInset: 96 },
  'abby-icon-book': { variantId: 'icon-512', width: 512, height: 512, transparentInset: 64 },
  'abby-icon-heart': { variantId: 'icon-512', width: 512, height: 512, transparentInset: 64 },
  'abby-icon-compass': { variantId: 'icon-512', width: 512, height: 512, transparentInset: 64 },
});

/** The build importer authenticates the manifest digest and complete payload.
 * Resolve only that pin; missing private files leave the ordinary DOM surface. */
export function stagedAchievementCardRelease(available = manifests, urls = files, lock = assetLock, indexes = manifestUrls) {
  const pin = lock.releases?.find((entry) => entry.family_id === ACHIEVEMENT_CARD_FAMILY);
  if (!pin) return null;
  const prefix = `./shared/${pin.directory}/`;
  const release = available[`${prefix}manifest.json`];
  const manifestUrl = indexes[`${prefix}manifest.json`];
  if (!release || !manifestUrl || release.family_id !== pin.family_id || release.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  const resolveUrl = (file) => urls[`${prefix}${file}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { release, resolveUrl, manifestUrl, manifestSha256: pin.manifest_sha256 };
}

/** This family contains PNGs only. Never send these selections to loadAsset,
 * whose portable runtime path accepts GLBs, or the older square UI resolver. */
export function resolveAchievementCardImage(assetId, variantId, staged = stagedAchievementCardRelease()) {
  if (!Object.hasOwn(ACHIEVEMENT_CARD_IMAGES, assetId) || !staged) return null;
  const geometry = ACHIEVEMENT_CARD_IMAGES[assetId];
  const selectedVariant = variantId ?? geometry.variantId;
  if (selectedVariant !== geometry.variantId) return null;
  const asset = staged.release.assets.find((entry) => entry.id === assetId && entry.kind === 'image');
  const variant = asset?.variants.find((entry) => entry.id === selectedVariant);
  if (!variant) return null;
  const file = staged.release.files.find((entry) => entry.path === variant.file && entry.media_type === 'image/png');
  const url = file && staged.resolveUrl(file.path);
  if (!url) return null;
  return { ...geometry, url, assetId, variantId: selectedVariant };
}
