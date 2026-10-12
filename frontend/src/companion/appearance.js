// Owned identities come from Django; these files provide appearance only.
// Optional globs let public validation builds work without private paid art.
const manifests = import.meta.glob('./licensed/manifest.json', { eager: true, import: 'default' });
const assets = import.meta.glob('./licensed/*.glb', { eager: true, query: '?url', import: 'default' });
const manifest = manifests['./licensed/manifest.json'];

export function resolveAppearance(creature, kind = 'pet', source = manifest, urls = assets) {
  if (!creature?.id || source?.schema_version !== 1) return null;
  const binding = source.bindings?.find((entry) =>
    entry.species_slug && entry.species_slug === creature.species?.slug
    && entry.species_sprite_key === creature.species?.sprite_key
    && entry.potion_slug === creature.potion?.slug);
  if (!binding) return null;
  const stage = kind === 'mount' ? 'mount' : creature.evolved_to_mount === true ? 'evolved' : 'pet';
  const modelKey = binding[stage];
  const model = source.models?.[modelKey];
  const url = model?.file && urls[`./licensed/${model.file}`];
  if (!url) return null;
  const woodland = source.models?.woodland;
  return {
    key: modelKey,
    url,
    idleClip: model.idle_clip || null,
    rotationY: model.rotation_y || 0,
    woodland: woodland?.file && urls[`./licensed/${woodland.file}`]
      ? { url: urls[`./licensed/${woodland.file}`], scale: woodland.scale || 1 }
      : null,
  };
}

export function creatureLabel(creature) {
  return [creature?.potion?.name, creature?.species?.name].filter(Boolean).join(' ');
}

export function activeCompanion(stable) {
  const pet = stable?.pets?.find((entry) => entry.is_active === true);
  if (pet) return { creature: pet, kind: 'pet' };
  const mount = stable?.mounts?.find((entry) => entry.is_active === true);
  return mount ? { creature: mount, kind: 'mount' } : null;
}
