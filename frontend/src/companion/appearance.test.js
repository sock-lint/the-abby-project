import { describe, expect, it } from 'vitest';
import { activeCompanion, resolveAppearance } from './appearance';

const manifest = {
  schema_version: 1,
  bindings: [{ species_slug: 'chick', species_sprite_key: 'cute-chick', potion_slug: 'base', pet: 'chick', evolved: 'bird', mount: 'bird' }],
  models: { chick: { file: 'chick.glb', idle_clip: 'Idle' }, bird: { file: 'bird.glb', idle_clip: 'Fly Idle' }, woodland: { file: 'woodland.glb' } },
};
const urls = { './licensed/chick.glb': '/chick.glb', './licensed/bird.glb': '/bird.glb', './licensed/woodland.glb': '/woodland.glb' };
const chick = { id: 7, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, growth_points: 100, evolved_to_mount: false };

describe('Owned companion appearance bindings', () => {
  it('requires confirmed evolution, independent of growth, and uses Bird for an actual mount', () => {
    expect(resolveAppearance(chick, 'pet', manifest, urls)?.key).toBe('chick');
    expect(resolveAppearance({ ...chick, evolved_to_mount: true }, 'pet', manifest, urls)?.key).toBe('bird');
    expect(resolveAppearance(chick, 'mount', manifest, urls)?.key).toBe('bird');
  });

  it('never substitutes a missing species, variant, identity or model with the bird', () => {
    expect(resolveAppearance({ ...chick, species: { sprite_key: 'fox' } }, 'pet', manifest, urls)).toBeNull();
    expect(resolveAppearance({ ...chick, species: { slug: 'different-species', sprite_key: 'cute-chick' } }, 'pet', manifest, urls)).toBeNull();
    expect(resolveAppearance({ ...chick, potion: { slug: 'fire' } }, 'pet', manifest, urls)).toBeNull();
    expect(resolveAppearance({ ...chick, id: null }, 'pet', manifest, urls)).toBeNull();
    expect(resolveAppearance(chick, 'pet', undefined, {})).toBeNull();
    expect(resolveAppearance(chick, 'pet', manifest, {})).toBeNull();
  });

  it('only previews server-selected active ownership and does not choose the first collection entry', () => {
    expect(activeCompanion({ pets: [chick], mounts: [] })).toBeNull();
    expect(activeCompanion({ pets: [chick, { ...chick, id: 8, is_active: true }] })?.creature.id).toBe(8);
    expect(activeCompanion({ pets: [], mounts: [{ ...chick, is_active: true }] })?.kind).toBe('mount');
  });

  it('exposes only known interactions with both a staged model and named supplied clip', () => {
    const source = structuredClone(manifest);
    source.models.chick.interaction_clips = {
      play: { file: 'hop.glb', clip: 'Jump Forward In Place' },
      left: { file: 'absent.glb', clip: 'Turn Left' },
      right: { file: 'hop.glb' },
      fight: { file: 'hop.glb', clip: 'Attack' },
    };
    expect(resolveAppearance(chick, 'pet', source, { ...urls, './licensed/hop.glb': '/hop.glb' }).interactions).toEqual({
      play: { url: '/hop.glb', clip: 'Jump Forward In Place' },
    });
  });
});
