import { isCatalogAvailable } from '../utils/catalogAvailability';
import { resolveSharedBirdAppearance } from './sharedBirdRelease';

// Owned identities come from Django; these files provide appearance only.
// Optional globs let public validation builds work without private paid art.
const manifests = import.meta.glob('./licensed/manifest.json', { eager: true, import: 'default' });
const assets = import.meta.glob('./licensed/*.glb', { eager: true, query: '?url', import: 'default' });
const manifest = manifests['./licensed/manifest.json'];

export function resolveAppearance(creature, kind = 'pet', source = manifest, urls = assets, shared) {
  const suppliedLegacy = source !== manifest || urls !== assets;
  const prepared = resolveSharedBirdAppearance(creature, kind, shared === undefined && suppliedLegacy ? null : shared);
  if (prepared) {
    const woodland = source?.models?.woodland;
    return { ...prepared, woodland: woodland?.file && urls[`./licensed/${woodland.file}`]
      ? { url: urls[`./licensed/${woodland.file}`], scale: woodland.scale || 1 } : null };
  }
  if (creature?.evolution_stage === 'fledgling') return null;
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
    interactions: Object.fromEntries(['play', 'left', 'right'].flatMap((action) => {
      const take = model.interaction_clips?.[action];
      const takeUrl = take?.file && urls[`./licensed/${take.file}`];
      return takeUrl && take.clip ? [[action, { url: takeUrl, clip: take.clip }]] : [];
    })),
    woodland: woodland?.file && urls[`./licensed/${woodland.file}`]
      ? { url: urls[`./licensed/${woodland.file}`], scale: woodland.scale || 1 }
      : null,
  };
}

export function creatureLabel(creature) {
  return [creature?.potion?.name, creature?.species?.name].filter(Boolean).join(' ');
}

export function preferredCompanion(stable) {
  const supportedPets = (stable?.pets || []).filter(isCatalogAvailable);
  const supportedMounts = (stable?.mounts || []).filter(isCatalogAvailable);
  const preferred = supportedPets.find((entry) => entry.is_active);
  if (preferred) return { creature: preferred, kind: 'pet' };
  const preferredMount = supportedMounts.find((entry) => entry.is_active);
  if (preferredMount) return { creature: preferredMount, kind: 'mount' };
  if (supportedPets[0]) return { creature: supportedPets[0], kind: 'pet' };
  if (supportedMounts[0]) return { creature: supportedMounts[0], kind: 'mount' };
  return activeCompanion(stable);
}

export function activeCompanion(stable) {
  const pet = stable?.pets?.find((entry) => entry.is_active === true);
  if (pet) return { creature: pet, kind: 'pet' };
  const mount = stable?.mounts?.find((entry) => entry.is_active === true);
  return mount ? { creature: mount, kind: 'mount' } : null;
}
