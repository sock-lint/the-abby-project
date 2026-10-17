import roster from '../../../shared/catalog/companion-roster.json';

export function rosterPet(lineage = 'wolf') {
  return { id: 9, species: { slug: `meshtint-${lineage}`, sprite_key: `meshtint-${lineage}`, name: lineage }, potion: { slug: 'base' }, lifecycle_stage: 'middle', growth_points: 65, evolved_to_mount: false };
}
export function rosterEgg() {
  return { id: 7, slug: 'meshtint-wolf-egg', item_type: 'egg', pet_species_slug: 'meshtint-wolf', metadata: { species: 'meshtint-wolf' } };
}
export function rosterFixture() {
  let index = 0;
  const files = [];
  const file = (extension) => {
    const sha256 = (++index).toString(16).padStart(64, '0'), path = `objects/${sha256}.${extension}`;
    files.push({ path, sha256, bytes: 100, media_type: extension === 'glb' ? 'model/gltf-binary' : 'image/png' });
    return path;
  };
  const animation = (actions) => ({ root_node: null, actions: Object.fromEntries(actions.map(([action, clip]) => [action, clip])), clips: actions.map(([, name, loop]) => ({ name, loop, duration: 1, root_motion: 'source', bounds: null })) });
  const model = (id, actions, defaultVariant = 'source-idle', egg = false) => ({
    id, label: id, kind: egg ? 'prop' : 'creature', capabilities: ['model', 'skinned', 'animated'], default_variant: defaultVariant,
    variants: egg ? [{ id: 'native', label: id, file: file('glb'), rig_adapter_id: `native-${id}`,
      bounds: { min: [-1, 0, -1], max: [1, 1, 1] }, animations: animation(actions) }]
      : actions.map(([action, clip, loop]) => ({ id: `source-${action === 'idle' && clip === 'Fly Idle' ? 'fly-idle' : action}`, label: clip, file: file('glb'), rig_adapter_id: `native-${id}-${action}`,
        bounds: { min: [-1, 0, -1], max: [1, id.endsWith('grown') ? 2 : 1, 1] }, animations: animation([[action, clip, loop]]) })),
  });
  const image = (id, egg = false) => ({ id, label: id, kind: 'image', capabilities: ['image'], default_variant: 'icon', variants: (egg ? ['icon'] : ['icon', 'native']).map((variant) => ({ id: variant, label: variant, file: file('png'), bounds: null, rig_adapter_id: null, animations: null })) });
  const assets = roster.families.filter(({ lineage_id }) => ['wolf', 'dragon'].includes(lineage_id)).flatMap((family) => [
    ...Object.entries(family.stages).flatMap(([stage, binding]) => [
      model(binding.asset_id, [['idle', family.lineage_id === 'dragon' && stage === 'middle' ? 'Fly Idle' : 'Idle', true], ['cast-spell', 'Cast Spell', false], ['turn-left', 'Turn Left', false]], binding.default_variant_id),
      image(binding.portrait_asset_id),
    ]),
    model(family.egg.asset_id, ['attack', 'bounce', 'cast-spell', 'die', 'idle', 'roll-forward-in-place', 'roll-forward-w-root', 'shake', 'spawn', 'take-damage', 'turn-left', 'turn-right', 'underground'].map((action) => [action, action === 'idle' ? 'Idle' : action === 'underground' ? 'Underground' : action, ['idle', 'underground', 'bounce'].includes(action)]), 'native', true),
    image(family.egg.portrait_asset_id, true),
  ]);
  return { pin: roster.release, release: { schema_version: 1, kind: 'asset-pack', family_id: roster.release.family_id, release_version: roster.release.release_version, label: 'Synthetic roster', assets, files, relationships: [] },
    manifestUrl: '/synthetic/roster.json', manifestSha256: roster.release.manifest_sha256, resolveUrl: (path) => `/synthetic/${path}` };
}
