import { describe, expect, it } from 'vitest';
import {
  ACHIEVEMENT_CARD_FAMILY, ACHIEVEMENT_CARD_IMAGES,
  resolveAchievementCardImage, stagedAchievementCardRelease,
} from './achievementCardKit';

// Synthetic manifests and URLs only; delivery evidence and artwork stay private.
function fixture() {
  const files = [];
  const assets = Object.entries(ACHIEVEMENT_CARD_IMAGES).map(([id, geometry], index) => {
    const sha256 = (index + 1).toString(16).padStart(64, '0');
    const file = `objects/${sha256}.png`;
    files.push({ path: file, sha256, bytes: 100, media_type: 'image/png' });
    return { id, label: id, kind: 'image', capabilities: ['image'], default_variant: geometry.variantId,
      variants: [{ id: geometry.variantId, label: geometry.variantId, file, rig_adapter_id: null, bounds: null, animations: null }] };
  });
  const release = { schema_version: 1, kind: 'asset-pack', family_id: ACHIEVEMENT_CARD_FAMILY,
    release_version: '1.0.0', label: 'Synthetic card kit', assets, files, relationships: [] };
  const pin = { family_id: ACHIEVEMENT_CARD_FAMILY, release_version: '1.0.0', manifest_sha256: 'a'.repeat(64), directory: 'synthetic/1.0.0/pin' };
  const prefix = `./shared/${pin.directory}/`;
  const available = { [`${prefix}manifest.json`]: release };
  const urls = Object.fromEntries(files.map((file) => [`${prefix}${file.path}`, `/synthetic/${file.path}`]));
  const indexes = { [`${prefix}manifest.json`]: '/synthetic/manifest.json' };
  const lock = { releases: [pin] };
  return { release, available, urls, indexes, lock, prefix };
}

describe('Achievement card kit image resolution', () => {
  it('requires the pinned family, version, valid manifest, manifest URL, and complete payload inventory', () => {
    const f = fixture();
    expect(stagedAchievementCardRelease(f.available, f.urls, f.lock, f.indexes)).toMatchObject({ manifestSha256: 'a'.repeat(64) });
    expect(stagedAchievementCardRelease(f.available, f.urls, { releases: [] }, f.indexes)).toBeNull();
    expect(stagedAchievementCardRelease({}, f.urls, f.lock, f.indexes)).toBeNull();
    expect(stagedAchievementCardRelease(f.available, f.urls, { releases: [{ ...f.lock.releases[0], release_version: '2.0.0' }] }, f.indexes)).toBeNull();
    expect(stagedAchievementCardRelease(f.available, f.urls, f.lock, {})).toBeNull();
    for (const changed of [{ family_id: 'other-family' }, { kind: 'avatar-family' }]) {
      expect(stagedAchievementCardRelease({ [`${f.prefix}manifest.json`]: { ...f.release, ...changed } }, f.urls, f.lock, f.indexes)).toBeNull();
    }
    const incomplete = { ...f.urls };
    delete incomplete[Object.keys(incomplete)[0]];
    expect(stagedAchievementCardRelease(f.available, incomplete, f.lock, f.indexes)).toBeNull();
  });

  it('resolves the seven declared native canvases with their own variants and resizing guides', () => {
    const f = fixture();
    const staged = stagedAchievementCardRelease(f.available, f.urls, f.lock, f.indexes);
    for (const [assetId, geometry] of Object.entries(ACHIEVEMENT_CARD_IMAGES)) {
      expect(resolveAchievementCardImage(assetId, undefined, staged)).toMatchObject({ assetId, ...geometry });
      expect(resolveAchievementCardImage(assetId, geometry.variantId, staged)).toMatchObject({ assetId, ...geometry });
    }
    expect(resolveAchievementCardImage('abby-card-base-wide', 'wide', staged)).toMatchObject({ width: 1024, height: 512, resizeInset: 64, contentInset: 96 });
    expect(resolveAchievementCardImage('abby-card-base-tall', 'tall', staged)).toMatchObject({ width: 1024, height: 1280, resizeInset: 64, contentInset: 96 });
    expect(resolveAchievementCardImage('abby-icon-book', 'icon-512', staged)).toMatchObject({ width: 512, height: 512, transparentInset: 64 });
  });

  it('rejects old IDs, shape substitutions, GLBs, undeclared PNGs, and absent payloads', () => {
    const f = fixture();
    const staged = stagedAchievementCardRelease(f.available, f.urls, f.lock, f.indexes);
    for (const [assetId, variantId] of [
      ['card-front-light', 'web'], ['constructor', 'wide'], ['abby-card-base-wide', 'tall'],
      ['abby-card-base-wide', 'web'], ['abby-icon-book', 'native'],
    ]) expect(resolveAchievementCardImage(assetId, variantId, staged)).toBeNull();
    expect(resolveAchievementCardImage('abby-card-base-wide', 'wide', null)).toBeNull();
    expect(resolveAchievementCardImage('abby-card-base-wide', 'wide', { ...staged, resolveUrl: () => undefined })).toBeNull();
    for (const release of [
      { ...f.release, assets: [] },
      { ...f.release, files: [] },
      { ...f.release, assets: f.release.assets.map((asset) => ({ ...asset, kind: 'model' })) },
      { ...f.release, files: f.release.files.map((file) => ({ ...file, media_type: 'model/gltf-binary' })) },
    ]) expect(resolveAchievementCardImage('abby-card-base-wide', 'wide', { ...staged, release })).toBeNull();
  });
});
