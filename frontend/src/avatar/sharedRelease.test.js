import { describe, expect, it } from 'vitest';
import { sharedAvatarConfiguration, stagedArcherRelease, resolveSharedAvatarAppearance } from './sharedRelease';

const family = 'meshtint-female-archer-pack-01';
const hash = 'a'.repeat(64);
const file = `objects/${hash}.glb`;
const reference = (id, extra = {}) => ({ id, file, sha256: hash, bytes: 100, ...extra });
const defaults = { body: '01', skin: 'fair', outfit: 'nature', head: '02', hair_style: '01', hair_color: 'black', face_style: '01', face_color: 'black' };
// Authored contract fixture, containing no purchased model or source metadata.
const manifest = {
  schema_version: 1, family_id: family, release_version: '1.0.1',
  files: [{ path: file, sha256: hash, bytes: 100, media_type: 'model/gltf-binary' }],
  appearance: {
    family_id: family, defaults,
    selectors: Object.fromEntries(Object.entries(defaults).map(([field, id]) => [field, [{ id }]])),
    rig_adapter_ids: ['rig-01'],
    base_variants: [reference('base', { body: '01', skin: 'fair', outfit: 'nature', rig_adapter_id: 'rig-01' })],
    modules: [
      reference('head', { category: 'head', head: '02', skin: 'fair', attachment_node: 'Head' }),
      reference('hair', { category: 'hair', hair_style: '01', hair_color: 'black', attachment_node: 'Head' }),
      reference('face', { category: 'face', face_style: '01', face_color: 'black', attachment_node: 'Head' }),
    ],
    equipment_overrides: [], textures: [], projectiles: [],
  },
  equipment_catalogs: [{ rig_adapter_id: 'rig-01', items: [] }],
  animations: { actions: { idle: 'Idle', jump: 'Jump' }, clips: ['Idle', 'Jump'].map((name) => ({ name, duration: 1, loop: name === 'Idle', root_motion: 'in-place' })) },
};
const directory = `${family}/1.0.1/${hash}`;
const prefix = `./shared/${directory}/`;
const lock = { schema_version: 1, releases: [{ family_id: family, release_version: '1.0.1', directory, manifest_sha256: hash }] };
const staged = () => stagedArcherRelease({ [`${prefix}manifest.json`]: manifest }, { [`${prefix}${file}`]: '/static/assets/base.glb' }, lock);

describe('shared Archer delivery adapter', () => {
  it('maps existing server preferences into portable appearance and equipment IDs', () => {
    const config = sharedAvatarConfiguration({ outfit_style: 'archer-03', skin_tone: 'tan', outfit: 'fire', head_style: 'head-01',
      hair_style: 'hair-04', hair_color: 'light', face_style: 'face-03', headwear_style: 'hood-mystical',
      mask_style: 'mask-undercover', bow_style: 'bow-greenhorn', quiver_style: 'quiver-angel' }, manifest);
    expect(config).toEqual({ schema_version: 2, family_id: family,
      appearance: { body: '03', skin: 'tan', outfit: 'fire', head: '01', hair_style: '04', hair_color: 'blonde', face_style: '03', face_color: 'blonde' },
      slots: { head: 'hood-mystical-fire', 'face-accessory': 'mask-undercover-fire', 'left-hand': 'bow-greenhorn', back: 'quiver-angel-fire' },
      emission_enabled: false,
    });
    expect(config).not.toHaveProperty('source');
    expect(sharedAvatarConfiguration({ bow_style: 'bow-vines', quiver_style: 'quiver-rook' }, manifest).slots)
      .toEqual({ 'left-hand': 'bow-vines-nature', back: 'quiver-rook' });
  });

  it('selects the pinned release and maps build URLs without changing saved preferences', () => {
    const source = staged();
    expect(source.pipeline).toBe('abby-assets');
    const selected = resolveSharedAvatarAppearance({}, source);
    expect(selected.url).toBe('/static/assets/base.glb');
    expect(selected.idleClip).toBe('Idle');
    expect(selected.configuration.appearance).toEqual(defaults);
    expect(selected.configuration.slots).toEqual({});
  });

  it('rejects missing files, mismatched releases, and an invalid manifest', () => {
    expect(stagedArcherRelease({ [`${prefix}manifest.json`]: manifest }, {}, lock)).toBeNull();
    expect(stagedArcherRelease({ [`${prefix}manifest.json`]: { ...manifest, release_version: '2.0.0' } }, {}, lock)).toBeNull();
    expect(stagedArcherRelease({ [`${prefix}manifest.json`]: { ...manifest, files: [] } }, {}, lock)).toBeNull();
    expect(stagedArcherRelease({}, {}, lock)).toBeNull();
    expect(resolveSharedAvatarAppearance({ bow_style: 'bow-myth' }, staged())).toBeNull();
  });
});
