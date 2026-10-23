// Synthetic binding metadata only: fake numbered payloads, no private artwork.
export const BEE_BAT_FAMILY = 'abby-elemental-bee-bat';
export const BEE_BAT_MANIFEST_SHA256 = '7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5';
export const BEE_BAT_MOTIONS = {
  'meshtint-bee': {
    baby: ['bite-attack', 'cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'projectile-attack', 'sting-attack', 'take-damage', 'turn-left', 'turn-right'],
    middle: ['cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'head-attack', 'idle', 'sting-attack', 'take-damage', 'turn-left', 'turn-right'],
    grown: ['cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'jab-right-attack', 'power-jab-attack', 'slice-left-attack', 'sting-attack', 'take-damage', 'turn-left', 'turn-right'],
  },
  'meshtint-bat': {
    baby: ['bite-attack', 'cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'projectile-attack', 'take-damage', 'turn-left', 'turn-right'],
    middle: ['bite-attack', 'cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'projectile-attack', 'take-damage', 'turn-left', 'turn-right'],
    grown: ['bite-attack', 'cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'kick-attack', 'projectile-attack', 'spin-attack-attack', 'take-damage', 'turn-left', 'turn-right'],
  },
};
export const BEE_BAT_REVIEW_ICONS = ['review-bee-fire-acquisition-icon', 'review-bee-ice-acquisition-icon',
  'review-bat-fire-acquisition-icon', 'review-bat-ice-acquisition-icon'];

export function stagedBeeBatFixture() {
  let index = 0;
  const files = [], assets = [], stages = [];
  const file = (image = false) => {
    const sha256 = (++index).toString(16).padStart(64, '0'), path = `objects/${sha256}.${image ? 'png' : 'glb'}`;
    files.push({ path, sha256, bytes: 100, media_type: image ? 'image/png' : 'model/gltf-binary' });
    return path;
  };
  const image = (id) => assets.push({ id, label: `Synthetic ${id}`, kind: 'image', capabilities: ['image'], default_variant: 'icon',
    variants: [{ id: 'icon', label: 'Synthetic icon', file: file(true), bounds: null, rig_adapter_id: null, animations: null }] });
  for (const [species, motions] of Object.entries(BEE_BAT_MOTIONS)) {
    for (const potion of ['fire', 'ice']) for (const [stage, names] of Object.entries(motions)) {
      const assetId = `${species}-${potion}-${stage}`, portraitId = `${assetId}-portrait`;
      image(portraitId);
      assets.push({ id: assetId, label: `Synthetic ${assetId}`, kind: 'creature', capabilities: ['model', 'skinned', 'animated'],
        default_variant: 'source-idle', variants: names.map((motion) => {
          const variantId = `source-${motion}`, modelFile = file(), clip = `Clip-${index}`;
          stages.push({ species_slug: species, potion_slug: potion, lifecycle_stage: stage, motion, asset_id: assetId,
            variant_id: variantId, action: motion, portrait_asset_id: portraitId, portrait_variant_id: 'icon' });
          return { id: variantId, label: `Synthetic ${motion}`, file: modelFile, rig_adapter_id: `native-${index}`,
            bounds: { min: [-0.5, 0, -0.5], max: [0.5, stage === 'grown' ? 1.5 : 0.75, 0.5] },
            animations: { root_node: null, actions: { [motion]: clip },
              clips: [{ name: clip, duration: 1, loop: motion === 'idle' || motion.startsWith('fly-'), root_motion: 'source', bounds: null }] } };
        }) });
    }
  }
  BEE_BAT_REVIEW_ICONS.forEach(image);
  return { release: { schema_version: 1, kind: 'asset-pack', family_id: BEE_BAT_FAMILY, release_version: '1.0.0',
    label: 'Synthetic Bee/Bat pack', files, assets, relationships: [], appearance_bindings: { schema_version: 1, stages, transitions: [] } },
    manifestUrl: '/synthetic-bee-bat/manifest.json', manifestSha256: BEE_BAT_MANIFEST_SHA256,
    resolveUrl: (path) => `/synthetic-bee-bat/${path}` };
}
