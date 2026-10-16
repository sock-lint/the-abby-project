import { describe, expect, it } from 'vitest';
import { resolveCatalogIcon, stagedCatalogRelease } from './sharedCatalogIcons';

const digest = 'a'.repeat(64);
const file = `objects/${digest}.png`;
const manifest = {
  schema_version: 1, kind: 'asset-pack', family_id: 'abby-catalog-icons', release_version: '1.0.0',
  label: 'Synthetic catalog', relationships: [],
  files: [{ path: file, bytes: 100, sha256: digest, media_type: 'image/png' }],
  assets: [{ id: 'item-meat', kind: 'image', label: 'Meat', capabilities: ['image'], default_variant: 'icon-256',
    variants: [{ id: 'icon-256', label: 'Icon', file, animations: null, bounds: null, rig_adapter_id: null }] }],
};
const pin = { family_id: manifest.family_id, release_version: '1.0.0', manifest_sha256: digest, directory: `abby-catalog-icons/1.0.0/${digest}` };
const prefix = `../avatar/shared/${pin.directory}/`;
const available = { [`${prefix}manifest.json`]: manifest };
const urls = { [`${prefix}${file}`]: '/static/assets/synthetic-icon.png' };
const lock = { releases: [pin] };

describe('private catalog image release', () => {
  it('resolves image paths beneath the exact pinned manifest for web and native URLs', () => {
    const staged = stagedCatalogRelease(available, urls, lock);
    expect(resolveCatalogIcon('item-meat', staged)).toEqual({ url: '/static/assets/synthetic-icon.png', label: 'Meat' });
    expect(resolveCatalogIcon('item-meat', stagedCatalogRelease(available, { [`${prefix}${file}`]: '/assets/native.png' }, lock)).url).toBe('/assets/native.png');
    expect(resolveCatalogIcon('food-meat', staged)).toBeNull();
    expect(resolveCatalogIcon(null, staged)).toBeNull();
  });
  it('retains fallbacks for missing, incomplete, wrong-family or wrong-version releases', () => {
    expect(stagedCatalogRelease(available, urls, { releases: [] })).toBeNull();
    expect(stagedCatalogRelease({}, urls, lock)).toBeNull();
    expect(stagedCatalogRelease(available, {}, lock)).toBeNull();
    for (const overrides of [{ family_id: 'other' }, { release_version: '2.0.0' }, { kind: 'avatar-family' }]) {
      expect(stagedCatalogRelease({ [`${prefix}manifest.json`]: { ...manifest, ...overrides } }, urls, lock)).toBeNull();
    }
    expect(resolveCatalogIcon('item-meat', null)).toBeNull();
  });
  it('never treats a model, animated member or unlisted path as a catalog PNG', () => {
    const resolve = (patch) => resolveCatalogIcon('item-meat', {
      release: { ...manifest, assets: [{ ...manifest.assets[0], ...patch }] }, resolveUrl: () => '/private/image.png',
    });
    expect(resolve({ kind: 'model' })).toBeNull();
    expect(resolve({ variants: [{ ...manifest.assets[0].variants[0], animations: { actions: { idle: 'Idle' } } }] })).toBeNull();
    expect(resolve({ variants: [{ ...manifest.assets[0].variants[0], file: '../outside.png' }] })).toBeNull();
  });
});
