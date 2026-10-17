import { describe, expect, it } from 'vitest';
import { PEDESTAL_FAMILY, PEDESTAL_IMAGE_IDS, resolvePedestalImage, stagedPedestalRelease } from './pedestalRelease';

// Synthetic paths and bytes only; purchased manifests and payloads stay private.
function fixture() {
  const files = [];
  const assets = PEDESTAL_IMAGE_IDS.map((id, index) => ({
    id, label: id, kind: 'image', capabilities: ['image'], default_variant: 'web',
    variants: (index < 16 ? ['web', 'native'] : ['web']).map((variantId, variantIndex) => {
      const sha256 = (index * 2 + variantIndex + 1).toString(16).padStart(64, '0');
      const file = `objects/${sha256}.png`;
      files.push({ path: file, sha256, bytes: 100, media_type: 'image/png' });
      return { id: variantId, label: variantId, file, rig_adapter_id: null, bounds: null, animations: null };
    }),
  }));
  const release = { schema_version: 1, kind: 'asset-pack', family_id: PEDESTAL_FAMILY,
    release_version: '1.0.1', label: 'Synthetic presentation pack', assets, files, relationships: [] };
  const pin = { family_id: PEDESTAL_FAMILY, release_version: '1.0.1', manifest_sha256: 'a'.repeat(64), directory: 'synthetic/1.0.1/pin' };
  const prefix = `../avatar/shared/${pin.directory}/`;
  const available = { [`${prefix}manifest.json`]: release };
  const urls = Object.fromEntries(files.map((file) => [`${prefix}${file.path}`, `/test/${file.path}`]));
  const indexes = { [`${prefix}manifest.json`]: '/test/manifest.json' };
  const lock = { releases: [pin] };
  return { release, available, urls, lock, indexes, prefix };
}

describe('Private pedestal and card release resolution', () => {
  it('requires the pinned family/version, valid manifest, manifest URL and complete payload inventory', () => {
    const f = fixture();
    expect(stagedPedestalRelease(f.available, f.urls, f.lock, f.indexes)?.manifestSha256).toBe('a'.repeat(64));
    expect(stagedPedestalRelease(f.available, f.urls, { releases: [] }, f.indexes)).toBeNull();
    expect(stagedPedestalRelease(f.available, f.urls, { releases: [{ ...f.lock.releases[0], release_version: '2.0.0' }] }, f.indexes)).toBeNull();
    expect(stagedPedestalRelease(f.available, f.urls, f.lock, {})).toBeNull();
    expect(stagedPedestalRelease({ [`${f.prefix}manifest.json`]: { ...f.release, kind: 'avatar-family' } }, f.urls, f.lock, f.indexes)).toBeNull();
    const incomplete = { ...f.urls };
    delete incomplete[Object.keys(incomplete)[0]];
    expect(stagedPedestalRelease(f.available, incomplete, f.lock, f.indexes)).toBeNull();
  });

  it('renders only declared image assets at their full canvas dimensions and defaults to web', () => {
    const f = fixture();
    const staged = stagedPedestalRelease(f.available, f.urls, f.lock, f.indexes);
    for (const assetId of PEDESTAL_IMAGE_IDS) {
      expect(resolvePedestalImage(assetId, 'web', staged)).toMatchObject({ assetId, variantId: 'web', width: 512, height: 512 });
    }
    expect(resolvePedestalImage('card-front-nature', 'native', staged)).toMatchObject({ variantId: 'native', width: 1024, height: 1024 });
    expect(resolvePedestalImage('star-lit', 'native', staged)).toMatchObject({ variantId: 'web', width: 512, height: 512 });
    expect(resolvePedestalImage('normal-egg', 'web', staged)).toBeNull();
    expect(resolvePedestalImage('card-front-nature', 'source', staged)).toBeNull();
    expect(resolvePedestalImage('card-front-nature', 'web', null)).toBeNull();
    expect(resolvePedestalImage('card-front-nature', 'web', { ...staged, resolveUrl: () => undefined })).toBeNull();
    expect(resolvePedestalImage('card-front-nature', 'web', { ...staged, release: { ...f.release, assets: [] } })).toBeNull();
    expect(resolvePedestalImage('card-front-nature', 'web', { ...staged, release: { ...f.release, files: [] } })).toBeNull();
  });
});
