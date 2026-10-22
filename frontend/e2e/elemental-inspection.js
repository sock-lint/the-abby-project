// Private browser inspection through the same pinned loader used by the app.
import { loadAsset, loadCompanionAppearance } from '@abby-assets/avatar-runtime';
import { stagedElementalRelease } from '../src/companion/sharedElementalRelease';
import { stagedRosterRelease } from '../src/companion/sharedRosterRelease';
import roster from '../../shared/catalog/companion-roster.json';

const requireValue = (value, message) => { if (!value) throw new Error(message); };
function resources(instance) {
  const result = { materials: new Set(), textures: new Set(), geometries: new Set() };
  instance.model.traverse((node) => {
    if (node.geometry) result.geometries.add(node.geometry);
    for (const material of Array.isArray(node.material) ? node.material : node.material ? [node.material] : []) {
      result.materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) result.textures.add(value);
    }
  });
  return result;
}
function snapshot(owned) {
  return JSON.stringify({
    materials: [...owned.materials].map((material) => [material.name, material.color?.toArray(), material.emissive?.toArray(), material.opacity]),
    textures: [...owned.textures].map((texture) => [texture.uuid, texture.repeat.toArray(), texture.offset.toArray()]),
  });
}

export async function inspectElementalMaterialIsolation() {
  const base = stagedRosterRelease(), elemental = stagedElementalRelease(undefined, undefined, undefined, undefined, 'abby-elemental-dragon-mushroom');
  requireValue(base && elemental, 'Both exact private releases are required for isolation inspection.');
  const groups = [];
  for (const species of ['meshtint-dragon', 'meshtint-mushroom']) {
    const family = roster.families.find((entry) => entry.species_slug === species);
    for (const stage of ['baby', 'middle', 'grown']) {
      const instances = [];
      try {
        const binding = family.stages[stage];
        instances.push(await loadAsset(base.release, { asset_id: binding.asset_id, variant_id: binding.default_variant_id }, { resolveUrl: base.resolveUrl }));
        for (const potion of ['fire', 'ice', 'fire']) instances.push(await loadCompanionAppearance(elemental.release,
          { family_id: elemental.release.family_id, species_slug: species, potion_slug: potion, lifecycle_stage: stage, motion: 'idle' },
          { resolveUrl: elemental.resolveUrl }));
        const owned = instances.map(resources), counts = owned.map((entry) => Object.fromEntries(Object.entries(entry).map(([key, values]) => [key, values.size])));
        for (let a = 0; a < owned.length; a++) {
          for (const key of ['materials', 'textures', 'geometries']) {
            requireValue(owned[a][key].size > 0, `Missing ${key} in ${species}/${stage}.`);
            for (let b = a + 1; b < owned.length; b++) requireValue([...owned[a][key]].every((value) => !owned[b][key].has(value)), `Shared ${key} in ${species}/${stage}.`);
          }
        }
        const before = owned.map(snapshot);
        for (const material of owned[1].materials) { material.color?.setRGB(0.1, 0.2, 0.3); material.opacity = 0.37; }
        for (const texture of owned[1].textures) texture.repeat.set(0.5, 0.5);
        requireValue(snapshot(owned[1]) !== before[1], 'Mutation probe did not affect the selected Fire instance.');
        for (const index of [0, 2, 3]) requireValue(snapshot(owned[index]) === before[index], 'Fire mutation leaked into another appearance or instance.');
        const disposed = owned.map(() => ({ materials: 0, textures: 0, geometries: 0 }));
        owned.forEach((entry, index) => Object.entries(entry).forEach(([key, values]) => values.forEach((value) => value.addEventListener('dispose', () => { disposed[index][key]++; }))));
        instances[1].dispose();
        for (const key of ['materials', 'textures', 'geometries']) requireValue(disposed[1][key] === owned[1][key].size, `Selected Fire ${key} did not dispose exactly once.`);
        for (const index of [0, 2, 3]) requireValue(Object.values(disposed[index]).every((count) => count === 0), 'Disposal leaked into another appearance or instance.');
        groups.push({ species, stage, instances: instances.length, resources: counts, independent: true, mutation_isolated: true, disposal_isolated: true });
      } finally { instances.forEach((instance) => instance.dispose()); }
    }
  }
  return { groups, instances: groups.reduce((count, group) => count + group.instances, 0), independent: true };
}
