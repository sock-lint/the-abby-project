// Entirely synthetic contract data, not the pending artwork or native-take
// inventory. Numbered fake files and deliberately different logical/native
// identities exercise the adapter before the asset session returns.
export const SNAKE_CRAB_FAMILY = 'abby-elemental-snake-hermit-crab';
export const SNAKE_CRAB_SPECIES = ['meshtint-snake', 'meshtint-hermit-crab'];
export const SNAKE_CRAB_REVIEW_ICONS = ['review-snake-fire-acquisition-icon', 'review-snake-ice-acquisition-icon',
  'review-hermit-crab-fire-acquisition-icon', 'review-hermit-crab-ice-acquisition-icon'];

export function stagedSnakeCrabFixture() {
  let index = 0;
  const files = [], assets = [], stages = [];
  const file = (image = false) => {
    const sha256 = (++index).toString(16).padStart(64, '0'), path = `objects/${sha256}.${image ? 'png' : 'glb'}`;
    files.push({ path, sha256, bytes: 100, media_type: image ? 'image/png' : 'model/gltf-binary' });
    return path;
  };
  const image = (id) => assets.push({ id, label: `Synthetic ${id}`, kind: 'image', capabilities: ['image'], default_variant: 'icon',
    variants: [{ id: 'icon', label: 'Synthetic icon', file: file(true), bounds: null, rig_adapter_id: null, animations: null }] });
  for (const species of SNAKE_CRAB_SPECIES) for (const potion of ['fire', 'ice']) for (const stage of ['baby', 'middle', 'grown']) {
    const assetId = `${species}-${potion}-${stage}`, portraitId = `${assetId}-portrait`;
    image(portraitId);
    const variants = [
      ['source-rest-take', 'rest_native', 'Rest Native', ['idle', 'rest-alias']],
      ['source-travel-take', 'travel_native', 'Travel Native', ['walk-forward-in-place']],
    ].map(([id, action, clip, motions]) => {
      const modelFile = file();
      for (const motion of motions) stages.push({ species_slug: species, potion_slug: potion, lifecycle_stage: stage, motion,
        asset_id: assetId, variant_id: id, action, portrait_asset_id: portraitId, portrait_variant_id: 'icon' });
      return { id, label: `Synthetic ${id}`, file: modelFile, rig_adapter_id: `synthetic-rig-${index}`,
        bounds: { min: [-0.5, 0, -0.5], max: [0.5, stage === 'grown' ? 1.5 : 0.75, 0.5] },
        animations: { root_node: null, actions: { [action]: clip },
          clips: [{ name: clip, duration: 1, loop: true, root_motion: 'source', bounds: null }] } };
    });
    assets.push({ id: assetId, label: `Synthetic ${assetId}`, kind: 'creature', capabilities: ['model', 'skinned', 'animated'],
      default_variant: 'source-rest-take', variants });
  }
  SNAKE_CRAB_REVIEW_ICONS.forEach(image);
  return { release: { schema_version: 1, kind: 'asset-pack', family_id: SNAKE_CRAB_FAMILY, release_version: '1.0.0',
    label: 'Synthetic Snake/Hermit Crab contract pack', files, assets, relationships: [],
    appearance_bindings: { schema_version: 1, stages, transitions: [] } },
  manifestUrl: '/synthetic-snake-crab/manifest.json', manifestSha256: '0'.repeat(64),
  resolveUrl: (path) => `/synthetic-snake-crab/${path}` };
}

export const snakeCrabCreature = (species, potion, stage = 'baby') => ({ id: 91, species: { slug: species, sprite_key: species },
  potion: { slug: potion, name: potion === 'fire' ? 'Fire' : 'Ice' }, lifecycle_stage: stage, growth_points: 100,
  evolved_to_mount: stage === 'grown' });
export const snakeCrabEgg = (species) => ({ id: 72, name: `${species} Egg`, item_type: 'egg', slug: `${species}-egg`,
  pet_species_slug: species, metadata: { species } });
