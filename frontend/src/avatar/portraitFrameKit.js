import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';

const manifests = import.meta.glob('./shared/abby-portrait-frame-kit/**/manifest.json', { eager: true, import: 'default' });
const manifestUrls = import.meta.glob('./shared/abby-portrait-frame-kit/**/manifest.json', { eager: true, query: '?url', import: 'default' });
const files = import.meta.glob('./shared/abby-portrait-frame-kit/**/*.png', { eager: true, query: '?url', import: 'default' });

export const PORTRAIT_FRAME_FAMILY = 'abby-portrait-frame-kit';
export const PORTRAIT_FRAME_PIN = Object.freeze({
  family_id: PORTRAIT_FRAME_FAMILY,
  release_version: '1.1.0',
  manifest_sha256: '9c2e4e3c67edc2fa639bd8d92ff27d5929c356b220ccd4868dd2a3550c25bb91',
  directory: 'abby-portrait-frame-kit/1.1.0/9c2e4e3c67edc2fa639bd8d92ff27d5929c356b220ccd4868dd2a3550c25bb91',
});

// These are existing catalog identities, never ownership or unlock rules.
export const PORTRAIT_FRAME_BINDINGS = Object.freeze({
  'frame-laurel': 'item-frame-laurel',
  'frame-steampunk': 'item-frame-steampunk',
  'frame-rune-circle': 'item-frame-rune-circle',
  'frame-cosmic': 'item-frame-cosmic',
  'frame-scholar': 'item-frame-scholar',
  'frame-pixel': 'item-frame-pixel',
});

export const PORTRAIT_FRAME_SIZES = Object.freeze([32, 40, 64, 96]);
export const PORTRAIT_FRAME_GEOMETRY = Object.freeze({ portraitInset: 17.578125, portraitDiameter: 64.84375 });

/** The standard build importer verifies every file digest. Runtime composition
 * accepts only that exact reviewed pin, valid manifest and complete URL inventory. */
export function stagedPortraitFrameRelease(available = manifests, urls = files, lock = assetLock, indexes = manifestUrls) {
  const pin = lock.releases?.find((entry) => entry.family_id === PORTRAIT_FRAME_FAMILY);
  if (!pin || Object.entries(PORTRAIT_FRAME_PIN).some(([key, value]) => pin[key] !== value)) return null;
  const prefix = `./shared/${pin.directory}/`;
  const release = available[`${prefix}manifest.json`];
  const manifestUrl = indexes[`${prefix}manifest.json`];
  if (!release || !manifestUrl || release.family_id !== pin.family_id || release.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  const resolveUrl = (file) => urls[`${prefix}${file}`];
  if (release.files.some((file) => file.media_type !== 'image/png' || !resolveUrl(file.path))) return null;
  return { release, resolveUrl, manifestUrl, manifestSha256: pin.manifest_sha256 };
}

/** Size is the complete canvas. Geometry tier depends on CSS size alone:
 * separately authored small art must never be replaced by downscaled detail art.
 * This is a PNG family, independent from the GLB/avatar/companion runtime. */
export function resolvePortraitFrameImage(frameSlug, cssSize = 64, devicePixelRatio = 1, staged = stagedPortraitFrameRelease()) {
  if (!Object.hasOwn(PORTRAIT_FRAME_BINDINGS, frameSlug) || !PORTRAIT_FRAME_SIZES.includes(cssSize) || !staged) return null;
  const density = Math.min(3, Math.max(1, Math.ceil(Number(devicePixelRatio) || 1)));
  const assetId = PORTRAIT_FRAME_BINDINGS[frameSlug];
  const variantId = `${cssSize < 64 ? 'small' : 'detail'}-${cssSize}-${density}x`;
  const asset = staged.release.assets.find((entry) => entry.id === assetId && entry.kind === 'image');
  const variant = asset?.variants.find((entry) => entry.id === variantId);
  const file = variant && staged.release.files.find((entry) => entry.path === variant.file && entry.media_type === 'image/png');
  const url = file && staged.resolveUrl(file.path);
  if (!url) return null;
  return { assetId, variantId, url, cssSize, density, width: cssSize * density, height: cssSize * density, ...PORTRAIT_FRAME_GEOMETRY };
}
