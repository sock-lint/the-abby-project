import { describe, expect, it } from 'vitest';
import bindings from '../../../shared/catalog/artwork-bindings.json';
import activeLock from '../../assets.lock.json';
import evaluationLock from '../../assets.evaluation.lock.json';
import { ARTWORK_FAMILY, BIRTHDAY_ARTWORK_ID, resolveArtworkImage, stagedArtworkRelease } from './sharedArtwork';

function fixture() {
  const semantic = structuredClone(bindings);
  const row = semantic.badges['10-Hour Club'];
  const file = `objects/${row.sha256}.png`;
  const manifest = {
    schema_version: 1, kind: 'asset-pack', family_id: ARTWORK_FAMILY, release_version: semantic.release_version,
    label: 'Synthetic artwork', relationships: [],
    files: [{ path: file, bytes: 79308, sha256: row.sha256, media_type: 'image/png' }],
    assets: [{ id: row.asset_id, kind: 'image', label: '10-Hour Club', capabilities: ['image'], default_variant: 'icon-256',
      variants: [{ id: 'icon-256', label: 'Icon', file, animations: null, bounds: null, rig_adapter_id: null }] }],
  };
  const pin = { family_id: ARTWORK_FAMILY, release_version: semantic.release_version,
    manifest_sha256: semantic.manifest_sha256,
    directory: `${ARTWORK_FAMILY}/${semantic.release_version}/${semantic.manifest_sha256}` };
  const prefix = `../avatar/shared/${pin.directory}/`;
  const available = { [`${prefix}manifest.json`]: manifest };
  const urls = { [`${prefix}${file}`]: '/static/assets/synthetic-badge.png' };
  const lock = { releases: [pin] };
  return { row, file, manifest, pin, prefix, available, urls, lock, semantic,
    stage: () => stagedArtworkRelease(available, urls, lock, semantic) };
}

describe('pinned completion artwork', () => {
  it('keeps the exact private Crown evaluation release outside the active application lock', () => {
    const activeFamilies = new Set(activeLock.releases.map((pin) => pin.family_id));
    expect(activeFamilies.has('abby-bird-accessory-pilot')).toBe(false);
    expect(evaluationLock.schema_version).toBe(1);
    expect(evaluationLock.releases.filter((pin) => pin.family_id === 'abby-bird-accessory-pilot')).toEqual([{
      directory: 'abby-bird-accessory-pilot/1.0.0/432e9298689baf87f059c7c8734bf85aefe395e749149827cb58d0bbe43d9720',
      family_id: 'abby-bird-accessory-pilot',
      manifest_sha256: '432e9298689baf87f059c7c8734bf85aefe395e749149827cb58d0bbe43d9720',
      release_version: '1.0.0',
    }]);
    expect(evaluationLock.releases.filter((pin) => activeFamilies.has(pin.family_id))).toEqual([]);
  });

  it('returns the approved image and digest metadata for web and native URLs', () => {
    const data = fixture();
    expect(resolveArtworkImage(data.row.asset_id, data.stage())).toEqual({
      url: '/static/assets/synthetic-badge.png', label: '10-Hour Club', asset_id: data.row.asset_id,
      variant_id: 'icon-256', family_id: ARTWORK_FAMILY, release_version: data.pin.release_version,
      manifest_sha256: data.pin.manifest_sha256, sha256: data.row.sha256, bytes: 79308,
    });
    data.urls[`${data.prefix}${data.file}`] = '/assets/native-badge.png';
    expect(resolveArtworkImage(data.row.asset_id, data.stage()).url).toBe('/assets/native-badge.png');
    expect(BIRTHDAY_ARTWORK_ID).toBe(bindings.birthday.asset_id);
  });

  it('keeps fallbacks for absent, duplicate, changed or malformed release pins', () => {
    for (const change of [
      (data) => { data.lock.releases = []; },
      (data) => { data.lock.releases.push({ ...data.pin }); },
      (data) => { data.pin.manifest_sha256 = 'a'.repeat(64); },
      (data) => { data.pin.release_version = '2.0.0'; },
      (data) => { data.pin.directory = '../another-release'; },
      (data) => { data.pin.family_id = 'another-family'; },
      (data) => { data.semantic.manifest_sha256 = 'b'.repeat(64); },
      (data) => { data.semantic.family_id = 'another-family'; },
    ]) {
      const data = fixture(); change(data);
      expect(data.stage()).toBeNull();
    }
    expect(stagedArtworkRelease({}, {}, {})).toBeNull();
    expect(stagedArtworkRelease({}, {}, { releases: {} })).toBeNull();
  });

  it('rejects a wrong, invalid, incomplete or non-image staged manifest', () => {
    for (const change of [
      (data) => { delete data.available[`${data.prefix}manifest.json`]; },
      (data) => { data.manifest.family_id = 'another-family'; },
      (data) => { data.manifest.release_version = '2.0.0'; },
      (data) => { data.manifest.kind = 'avatar-family'; },
      (data) => { data.manifest.assets[0].kind = 'prop'; },
      (data) => { data.manifest.files[0].media_type = 'model/gltf-binary'; },
      (data) => { delete data.urls[`${data.prefix}${data.file}`]; },
      (data) => { data.semantic.categories.Coding = { ...data.row }; },
    ]) {
      const data = fixture(); change(data);
      expect(data.stage()).toBeNull();
    }
  });

  it('requires an exact semantic image binding rather than an arbitrary PNG in the pack', () => {
    const data = fixture();
    const staged = data.stage();
    for (const id of [null, undefined, 42, {}, '', '10-Hour Club', 'food-meat', 'constructor']) {
      expect(resolveArtworkImage(id, staged)).toBeNull();
    }
    expect(resolveArtworkImage(data.row.asset_id, null)).toBeNull();
    data.manifest.assets[0].id = 'unbound-new-image';
    expect(resolveArtworkImage('unbound-new-image', data.stage())).toBeNull();
  });

  it('fails closed when image variants, rig metadata or approved PNG bytes drift', () => {
    for (const change of [
      (data) => { data.row.sha256 = 'a'.repeat(64); },
      (data) => { data.row.sha256 = 'invalid'; },
      (data) => { data.row.family_id = 'another-family'; },
      (data) => { data.row.variant_id = 'native'; },
      (_data, staged) => { staged.manifest.assets[0].kind = 'prop'; },
      (_data, staged) => { staged.manifest.assets[0].variants[0].id = 'native'; },
      (_data, staged) => { staged.manifest.assets[0].variants[0].animations = {}; },
      (_data, staged) => { staged.manifest.assets[0].variants[0].rig_adapter_id = 'a-rig'; },
      (_data, staged) => { staged.manifest.assets[0].variants[0].bounds = { min: [0, 0, 0], max: [1, 1, 1] }; },
      (_data, staged) => { staged.manifest.assets[0].variants[0].file = '../outside.png'; },
      (_data, staged) => { staged.manifest.files[0].sha256 = 'b'.repeat(64); },
      (_data, staged) => { staged.manifest.files[0].path = `other/${staged.manifest.files[0].sha256}.png`; },
      (_data, staged) => { staged.manifest.files[0].media_type = 'model/gltf-binary'; },
      (_data, staged) => { staged.manifest.files[0].bytes = 0; },
      (data) => { data.urls[`${data.prefix}${data.file}`] = ''; },
      (_data, staged) => { staged.pin.manifest_sha256 = 'c'.repeat(64); },
    ]) {
      const data = fixture(), staged = data.stage(); change(data, staged);
      expect(resolveArtworkImage(data.row.asset_id, staged)).toBeNull();
    }
  });
});
