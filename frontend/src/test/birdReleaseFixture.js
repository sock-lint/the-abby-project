// Synthetic metadata exercises the released 31-motion/2-transition contract.
// The numbered files contain no purchased artwork or source filenames.
export function birdReleaseFixture() {
  let index = 0;
  const files = [];
  const actions = {
    chick: [['attack', false], ['cast', false], ['die', false], ['idle', true], ['jump', true], ['jump_root_motion', true], ['take_damage', false], ['turn_left', false], ['turn_right', false]],
    fledgling: [['attack', false], ['cast', false], ['die', false], ['idle_alternate', true], ['idle', true], ['run', true], ['run_root_motion', true], ['take_damage', false], ['turn_left', false], ['turn_right', false], ['walk', true], ['walk_root_motion', true]],
    bird: [['attack', false], ['cast', false], ['die', false], ['fly', true], ['fly_root_motion', true], ['idle', true], ['projectile_attack', false], ['take_damage', false], ['turn_left', false], ['turn_right', false]],
    'evolve-chick-to-fledgling': [['evolve', false]],
    'evolve-fledgling-to-bird': [['evolve', false]],
  };
  const assets = Object.entries(actions).map(([id, clips]) => ({
    id, label: id, kind: id.startsWith('evolve-') ? 'animation-library' : 'creature',
    capabilities: ['model', 'skinned', 'animated'], default_variant: id.startsWith('evolve-') ? 'authored' : 'source-idle',
    variants: clips.map(([action, loop]) => {
      const sha256 = (++index).toString(16).padStart(64, '0');
      const file = `objects/${sha256}.glb`;
      files.push({ path: file, sha256, bytes: 100, media_type: 'model/gltf-binary' });
      return {
        id: action === 'evolve' ? 'authored' : `source-${action.replaceAll('_', '-')}`,
        label: action.replaceAll('_', ' '), file, rig_adapter_id: `native-${id}-${action}`,
        bounds: { min: [-0.5, 0, -0.5], max: [0.5, id === 'bird' ? 1.5 : 0.75, 0.5] },
        animations: { root_node: null, actions: { [action]: action },
          clips: [{ name: action, duration: 1, loop, root_motion: 'source', bounds: null }] },
      };
    }),
  }));
  return {
    schema_version: 1, kind: 'asset-pack', family_id: 'meshtint-bird-evolution', release_version: '1.0.0', label: 'Synthetic bird pack', assets, files,
    relationships: [['chick', 'fledgling'], ['fledgling', 'bird']].map(([from, to]) => ({
      type: 'evolution', from_asset_id: from, to_asset_id: to,
      transition: { asset_id: `evolve-${from}-to-${to}`, variant_id: 'authored', action: 'evolve' },
    })),
  };
}

export const syntheticBird = { id: 9, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, growth_points: 100, evolved_to_mount: false };

export function stagedBirdFixture() {
  const release = birdReleaseFixture();
  return { release, manifestUrl: '/synthetic/manifest.json', manifestSha256: 'a'.repeat(64), resolveUrl: (file) => `/synthetic/${file}` };
}
