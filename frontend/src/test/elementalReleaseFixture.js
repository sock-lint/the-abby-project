// Synthetic binding metadata only: fake numbered payloads, no private artwork.
const BIRD_MOTIONS = {
  baby: ['bite-attack', 'cast-spell', 'die', 'idle', 'jump-forward-in-place', 'jump-forward-w-root', 'take-damage', 'turn-left', 'turn-right'],
  middle: ['bite-attack', 'cast-spell', 'die', 'idle-02', 'idle', 'run-forward-in-place', 'run-forward-w-root', 'take-damage', 'turn-left', 'turn-right', 'walk-forward-in-place', 'walk-forward-w-root'],
  grown: ['bite-attack', 'cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'projectile-attack', 'take-damage', 'turn-left', 'turn-right'],
};
const WOLF_MOTIONS = {
  baby: ['bite-attack', 'cast-spell', 'die', 'idle-happy', 'idle', 'jump-in-place', 'jump-w-root', 'pounce-and-bite-attack-in-place', 'pounce-and-bite-attack-w-root', 'projectile-attack', 'run-forward-in-place', 'run-forward-w-root', 'take-damage', 'turn-left', 'turn-right', 'walk-forward-in-place', 'walk-forward-w-root'],
  middle: ['bite-attack', 'cast-spell', 'die', 'happy', 'idle', 'jump-in-place', 'jump-w-root', 'look-left-right', 'pounce-attack-in-place', 'pounce-attack-w-root', 'projectile-attack', 'run-forward-in-place', 'run-forward-w-root', 'sniff', 'take-damage', 'turn-left', 'turn-right', 'walk-forward-in-place', 'walk-forward-w-root'],
  grown: ['bite-attack', 'cast-spell', 'die', 'idle', 'jump-forward-in-place', 'jump-forward-w-root', 'jump-in-place', 'jump-w-root', 'left-slash-attack', 'look-left-right', 'pounce-smash-attack-in-place', 'pounce-smash-attack-w-root', 'projectile-attack', 'right-slash-attack', 'run-forward-in-place', 'run-forward-w-root', 'smash-attack', 'take-damage', 'turn-left', 'turn-right', 'walk-forward-in-place', 'walk-forward-w-root'],
};
const BIRD_ACTIONS = { 'bite-attack': 'attack', 'cast-spell': 'cast', 'idle-02': 'idle_alternate',
  'jump-forward-in-place': 'jump', 'jump-forward-w-root': 'jump_root_motion', 'take-damage': 'take_damage', 'turn-left': 'turn_left', 'turn-right': 'turn_right',
  'run-forward-in-place': 'run', 'run-forward-w-root': 'run_root_motion', 'walk-forward-in-place': 'walk', 'walk-forward-w-root': 'walk_root_motion',
  'fly-forward-in-place': 'fly', 'fly-forward-w-root': 'fly_root_motion', 'projectile-attack': 'projectile_attack' };

export function elementalReleaseFixture() {
  let index = 0;
  const files = [], assets = [], stages = [], transitions = [], relationships = [];
  const file = (image = false) => {
    const sha256 = (++index).toString(16).padStart(64, '0'), path = `objects/${sha256}.${image ? 'png' : 'glb'}`;
    files.push({ path, sha256, bytes: 100, media_type: image ? 'image/png' : 'model/gltf-binary' });
    return path;
  };
  const model = (id, variants, transition = false) => ({ id, label: `Synthetic ${id}`, kind: transition ? 'animation-library' : 'creature',
    capabilities: ['model', 'skinned', 'animated'], default_variant: transition ? 'authored' : 'source-idle', variants });
  const variant = (id, action, loop, height = 1) => ({ id, label: `Synthetic ${id}`, file: file(), rig_adapter_id: `native-${index}`,
    bounds: { min: [-0.5, 0, -0.5], max: [0.5, height, 0.5] },
    animations: { root_node: null, actions: { [action]: `Clip-${index}` },
      clips: [{ name: `Clip-${index}`, duration: 1, loop, root_motion: 'source', bounds: null }] } });
  for (const [species, motions] of Object.entries({ chick: BIRD_MOTIONS, 'meshtint-wolf': WOLF_MOTIONS })) {
    for (const potion of ['fire', 'ice']) {
      for (const [stage, names] of Object.entries(motions)) {
        const id = `${species}-${potion}-${stage}`, portraitId = `${id}-portrait`;
        assets.push({ id: portraitId, label: 'Synthetic portrait', kind: 'image', capabilities: ['image'], default_variant: 'icon',
          variants: [{ id: 'icon', label: 'Synthetic icon', file: file(true), bounds: null, rig_adapter_id: null, animations: null }] });
        assets.push(model(id, names.map((motion) => {
          const action = species === 'chick' ? BIRD_ACTIONS[motion] || motion : motion;
          const idVariant = `source-${motion}`;
          stages.push({ species_slug: species, potion_slug: potion, lifecycle_stage: stage, motion, asset_id: id, variant_id: idVariant,
            action, portrait_asset_id: portraitId, portrait_variant_id: 'icon' });
          return variant(idVariant, action, ['idle', 'idle-02', 'idle-happy'].includes(motion) || /^(jump|walk|run|fly)-/.test(motion), stage === 'grown' ? 1.5 : 0.75);
        })));
      }
      if (species === 'chick') {
        for (const [from, to] of [['baby', 'middle'], ['middle', 'grown']]) {
          const id = `${species}-${potion}-${from}-to-${to}`;
          assets.push(model(id, [variant('authored', 'evolve', false)], true));
          transitions.push({ species_slug: species, potion_slug: potion, from_stage: from, to_stage: to, asset_id: id, variant_id: 'authored', action: 'evolve' });
          relationships.push({ type: 'evolution', from_asset_id: `${species}-${potion}-${from}`, to_asset_id: `${species}-${potion}-${to}`,
            transition: { asset_id: id, variant_id: 'authored', action: 'evolve' } });
        }
      }
    }
  }
  for (const id of ['item-fire-potion', 'item-ice-potion', 'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail']) {
    assets.push({ id, label: `Synthetic ${id}`, kind: 'image', capabilities: ['image'], default_variant: 'icon',
      variants: [{ id: 'icon', label: 'Synthetic icon', file: file(true), bounds: null, rig_adapter_id: null, animations: null }] });
  }
  return { schema_version: 1, kind: 'asset-pack', family_id: 'abby-elemental-companions', release_version: '1.0.0', label: 'Synthetic elemental pack',
    files, assets, relationships, appearance_bindings: { schema_version: 1, stages, transitions } };
}

export function stagedElementalFixture() {
  return { release: elementalReleaseFixture(), manifestUrl: '/synthetic-elemental/manifest.json',
    manifestSha256: 'fe271f2ef6909dec7cb6fb44dc70635bd7efbb9bf01a1f74052065fcce675048', resolveUrl: (path) => `/synthetic-elemental/${path}` };
}

export function syntheticElemental(species = 'chick', potion = 'fire', stage = 'baby') {
  return { id: 19, species: { slug: species, sprite_key: species === 'chick' ? 'cute-chick' : species, name: species === 'chick' ? 'Chick' : 'Wolf' },
    potion: { slug: potion, name: potion === 'fire' ? 'Fire' : 'Ice' }, lifecycle_stage: stage, growth_points: stage === 'baby' ? 49 : stage === 'middle' ? 50 : 100,
    evolved_to_mount: stage === 'grown' };
}
