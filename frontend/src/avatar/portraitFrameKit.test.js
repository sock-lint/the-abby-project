import { describe, expect, it } from 'vitest';
import {
  PORTRAIT_FRAME_FAMILY, PORTRAIT_FRAME_PIN, PORTRAIT_FRAME_BINDINGS,
  stagedPortraitFrameRelease, resolvePortraitFrameImage,
} from './portraitFrameKit';

// Synthetic content-addressed files exercise the receiving contract. The
// private manifest, purchased artwork and source paths stay outside Git.
function fixture() {
  const files = [];
  const assets = Object.values(PORTRAIT_FRAME_BINDINGS).map((id, assetIndex) => {
    const variants = [32, 40, 64, 96].flatMap((size, sizeIndex) => [1, 2, 3].map((density) => {
      const sha256 = (assetIndex * 12 + sizeIndex * 3 + density).toString(16).padStart(64, '0');
      const file = `objects/${sha256}.png`;
      const variantId = `${size < 64 ? 'small' : 'detail'}-${size}-${density}x`;
      files.push({ path: file, sha256, bytes: 100, media_type: 'image/png' });
      return { id: variantId, label: variantId, file, rig_adapter_id: null, bounds: null, animations: null };
    }));
    return { id, label: id, kind: 'image', capabilities: ['image'], default_variant: 'detail-64-2x', variants };
  });
  const release = { schema_version: 1, kind: 'asset-pack', family_id: PORTRAIT_FRAME_FAMILY,
    release_version: PORTRAIT_FRAME_PIN.release_version, label: 'Synthetic portrait kit', assets, files, relationships: [] };
  const prefix = `./shared/${PORTRAIT_FRAME_PIN.directory}/`;
  const available = { [`${prefix}manifest.json`]: release };
  const urls = Object.fromEntries(files.map((file) => [`${prefix}${file.path}`, `/synthetic/${file.path}`]));
  const indexes = { [`${prefix}manifest.json`]: '/synthetic/manifest.json' };
  const lock = { releases: [PORTRAIT_FRAME_PIN] };
  return { release, prefix, available, urls, indexes, lock };
}

describe('Portrait frame kit', () => {
  it('requires the exact reviewed release pin and complete valid PNG inventory', () => {
    const f = fixture();
    expect(stagedPortraitFrameRelease(f.available, f.urls, f.lock, f.indexes)).toMatchObject({ manifestSha256: PORTRAIT_FRAME_PIN.manifest_sha256 });
    expect(stagedPortraitFrameRelease(f.available, f.urls, { releases: [] }, f.indexes)).toBeNull();
    expect(stagedPortraitFrameRelease({}, f.urls, f.lock, f.indexes)).toBeNull();
    expect(stagedPortraitFrameRelease(f.available, f.urls, f.lock, {})).toBeNull();
    for (const change of [{ release_version: '1.0.0' }, { manifest_sha256: 'f'.repeat(64) }, { directory: 'another/release' }]) {
      expect(stagedPortraitFrameRelease(f.available, f.urls, { releases: [{ ...PORTRAIT_FRAME_PIN, ...change }] }, f.indexes)).toBeNull();
    }
    for (const change of [{ family_id: 'another-family' }, { kind: 'avatar-family' }, { release_version: '1.0.0' }]) {
      expect(stagedPortraitFrameRelease({ [`${f.prefix}manifest.json`]: { ...f.release, ...change } }, f.urls, f.lock, f.indexes)).toBeNull();
    }
    const incomplete = { ...f.urls };
    delete incomplete[Object.keys(incomplete)[0]];
    expect(stagedPortraitFrameRelease(f.available, incomplete, f.lock, f.indexes)).toBeNull();
  });

  it('chooses separately authored small art at 32/40 and detail art at 64/96 for every exact catalog frame', () => {
    const f = fixture();
    const staged = stagedPortraitFrameRelease(f.available, f.urls, f.lock, f.indexes);
    for (const [slug, assetId] of Object.entries(PORTRAIT_FRAME_BINDINGS)) {
      for (const size of [32, 40, 64, 96]) {
        expect(resolvePortraitFrameImage(slug, size, 2, staged)).toMatchObject({
          assetId, cssSize: size, width: size * 2, height: size * 2,
          variantId: `${size < 64 ? 'small' : 'detail'}-${size}-2x`,
          portraitInset: 17.578125, portraitDiameter: 64.84375,
        });
      }
    }
  });

  it.each([[0, 1], [0.8, 1], [1, 1], [1.1, 2], [1.9, 2], [2.01, 3], [4, 3]])('rounds DPR %s upward and clamps to density %s', (dpr, density) => {
    const f = fixture();
    const staged = stagedPortraitFrameRelease(f.available, f.urls, f.lock, f.indexes);
    expect(resolvePortraitFrameImage('frame-laurel', 40, dpr, staged)).toMatchObject({ variantId: `small-40-${density}x` });
  });

  it('rejects unknown frames, namespace lookalikes, unsupported canvases, missing variants and non-PNG files', () => {
    const f = fixture();
    const staged = stagedPortraitFrameRelease(f.available, f.urls, f.lock, f.indexes);
    for (const slug of ['frame-bronze', 'custom-frame-laurel', 'constructor', null]) expect(resolvePortraitFrameImage(slug, 64, 1, staged)).toBeNull();
    for (const size of [24, 36, 80, 128]) expect(resolvePortraitFrameImage('frame-laurel', size, 1, staged)).toBeNull();
    expect(resolvePortraitFrameImage('frame-laurel', 64, 1, null)).toBeNull();
    expect(resolvePortraitFrameImage('frame-laurel', 64, 1, { ...staged, resolveUrl: () => undefined })).toBeNull();
    for (const release of [
      { ...f.release, assets: [] },
      { ...f.release, assets: f.release.assets.map((asset) => ({ ...asset, kind: 'model' })) },
      { ...f.release, assets: f.release.assets.map((asset) => ({ ...asset, variants: asset.variants.filter((variant) => variant.id !== 'detail-64-1x') })) },
      { ...f.release, files: f.release.files.map((file) => ({ ...file, media_type: 'model/gltf-binary' })) },
    ]) expect(resolvePortraitFrameImage('frame-laurel', 64, 1, { ...staged, release })).toBeNull();
  });
});
