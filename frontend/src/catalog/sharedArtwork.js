import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';
import artworkBindings from '../../../shared/catalog/artwork-bindings.json';

const manifests = import.meta.glob('../avatar/shared/abby-artwork-completion/**/manifest.json', { eager: true, import: 'default' });
const files = import.meta.glob('../avatar/shared/abby-artwork-completion/**/*.png', { eager: true, query: '?url', import: 'default' });

export const ARTWORK_FAMILY = 'abby-artwork-completion';
export const BIRTHDAY_ARTWORK_ID = 'birthday-candle';

function matchesPin(pin, bindings) {
  return pin?.family_id === ARTWORK_FAMILY && bindings?.family_id === ARTWORK_FAMILY
    && pin.release_version === bindings.release_version && pin.manifest_sha256 === bindings.manifest_sha256
    && /^[a-f0-9]{64}$/.test(pin.manifest_sha256)
    && pin.directory === `${ARTWORK_FAMILY}/${pin.release_version}/${pin.manifest_sha256}`;
}

function imageBindings(bindings) {
  return [
    ...Object.values(bindings.badges || {}), ...Object.values(bindings.categories || {}),
    ...Object.values(bindings.subjects || {}).flatMap((category) => Object.values(category)),
    ...Object.values(bindings.skills || {}).flatMap((category) => Object.values(category)),
    ...Object.values(bindings.items || {}), ...Object.values(bindings.challenges || {}), bindings.birthday,
  ].filter(Boolean);
}

/** Only the exact semantic-map pin may supply artwork. Import/build verification
 * authenticates the manifest and payload bytes; this adapter also checks every
 * selected PNG's digest against its code-only identity binding. */
export function stagedArtworkRelease(available = manifests, urls = files, lock = assetLock, bindings = artworkBindings) {
  const pins = Array.isArray(lock?.releases) ? lock.releases.filter((entry) => entry?.family_id === ARTWORK_FAMILY) : [];
  if (pins.length !== 1 || !matchesPin(pins[0], bindings)) return null;
  const pin = pins[0], prefix = `../avatar/shared/${pin.directory}/`;
  const manifest = available?.[`${prefix}manifest.json`];
  if (!manifest || manifest.family_id !== pin.family_id || manifest.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(manifest); } catch { return null; }
  if (manifest.assets.some((asset) => asset.kind !== 'image')
    || manifest.files.some((file) => file.media_type !== 'image/png' || !urls?.[`${prefix}${file.path}`])) return null;
  const rows = imageBindings(bindings);
  if (new Set(rows.map((row) => row.asset_id)).size !== rows.length) return null;
  return { pin, manifest, bindings, rows: new Map(rows.map((row) => [row.asset_id, row])),
    resolveUrl: (relative) => urls[`${prefix}${relative}`] ?? null };
}

const installed = stagedArtworkRelease();

/** The API supplies catalog IDs after exact record matching. Missing private
 * art, unsupported image metadata and semantic digest drift all keep fallbacks. */
export function resolveArtworkImage(assetId, staged = installed) {
  if (typeof assetId !== 'string' || !staged || !matchesPin(staged.pin, staged.bindings)) return null;
  const row = staged.rows?.get(assetId);
  if (!row || row.family_id !== ARTWORK_FAMILY || row.variant_id !== 'icon-256' || !/^[a-f0-9]{64}$/.test(row.sha256)) return null;
  const asset = staged.manifest.assets.find((entry) => entry.id === assetId);
  const variant = asset?.variants.find((entry) => entry.id === row.variant_id);
  if (asset?.kind !== 'image' || !variant || variant.animations !== null || variant.rig_adapter_id !== null || variant.bounds !== null) return null;
  const file = staged.manifest.files.find((entry) => entry.path === variant.file);
  const objectDigest = /^objects\/([a-f0-9]{64})\.png$/.exec(file?.path || '')?.[1];
  if (file?.media_type !== 'image/png' || !objectDigest || objectDigest !== file.sha256 || file.sha256 !== row.sha256
    || !Number.isSafeInteger(file.bytes) || file.bytes <= 0) return null;
  const url = staged.resolveUrl(file.path);
  return typeof url === 'string' && url ? {
    url, label: asset.label, asset_id: asset.id, variant_id: variant.id, family_id: ARTWORK_FAMILY,
    release_version: staged.pin.release_version, manifest_sha256: staged.pin.manifest_sha256,
    sha256: file.sha256, bytes: file.bytes,
  } : null;
}
