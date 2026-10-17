import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';

const manifests = import.meta.glob('../avatar/shared/abby-catalog-icons/**/manifest.json', { eager: true, import: 'default' });
const files = import.meta.glob('../avatar/shared/abby-catalog-icons/**/*.png', { eager: true, query: '?url', import: 'default' });
const FAMILY = 'abby-catalog-icons';

/** Build/import verification checks the digest and every byte. Only that lock's
 * manifest directory supplies URLs; workshop provenance paths are never URLs. */
export function stagedCatalogRelease(available = manifests, urls = files, lock = assetLock) {
  const pin = lock.releases?.find((entry) => entry.family_id === FAMILY);
  if (!pin) return null;
  const prefix = `../avatar/shared/${pin.directory}/`;
  const release = available[`${prefix}manifest.json`];
  if (!release || release.family_id !== pin.family_id || release.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  const resolveUrl = (path) => urls[`${prefix}${path}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { release, resolveUrl };
}

const installed = stagedCatalogRelease();

/** assetId is supplied by Django after matching an actual catalog record.
 * Sprite slugs, display names and numeric database IDs never select this art. */
export function resolveCatalogIcon(assetId, staged = installed) {
  if (!assetId || !staged) return null;
  const asset = staged.release.assets.find((entry) => entry.id === assetId);
  const variant = asset?.variants.find((entry) => entry.id === 'icon-256');
  if (asset?.kind !== 'image' || !variant || variant.animations != null) return null;
  const file = staged.release.files.find((entry) => entry.path === variant.file);
  if (file?.media_type !== 'image/png' || !/^objects\/[a-f0-9]{64}\.png$/.test(file.path)) return null;
  const url = staged.resolveUrl(file.path);
  return url ? { url, label: asset.label } : null;
}
