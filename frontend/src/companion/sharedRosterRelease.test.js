import { describe, expect, it } from 'vitest';
import { resolveAppearance } from './appearance';
import { resolveRosterAppearance, resolveRosterEggAppearance, resolveRosterPortrait, rosterMotions, stagedRosterRelease } from './sharedRosterRelease';
import { rosterFixture, rosterPet, rosterEgg } from '../test/rosterReleaseFixture';

describe('Exact staged companion roster bindings', () => {
  it('selects only exact species, sprite, Base and confirmed lifecycle stages', () => {
    const staged = rosterFixture();
    expect(resolveRosterAppearance(rosterPet(), 'pet', staged)?.assetId).toBe('wolf-middle');
    for (const changed of [{ id: null }, { species: { slug: 'wolf', sprite_key: 'meshtint-wolf' } }, { potion: { slug: 'fire' } }, { lifecycle_stage: 'unknown' }, { lifecycle_stage: undefined }, { lifecycle_stage: 'grown', evolved_to_mount: false }, { species: { slug: 'meshtint-training-dummy', sprite_key: 'meshtint-training-dummy' } }]) {
      expect(resolveRosterAppearance({ ...rosterPet(), ...changed }, 'pet', staged)).toBeNull();
    }
    expect(resolveRosterAppearance({ ...rosterPet(), evolved_to_mount: true }, 'pet', staged)?.assetId).toBe('wolf-grown');
  });

  it('uses the Dragon Fire Fly Idle default without inventing ground locomotion', () => {
    const staged = rosterFixture();
    const appearance = resolveRosterAppearance(rosterPet('dragon'), 'pet', staged);
    expect(appearance).toMatchObject({ assetId: 'dragon-middle', defaultVariantId: 'source-fly-idle', defaultAction: 'idle' });
    expect(appearance.motions.some(({ action }) => action === 'walk' || action === 'run')).toBe(false);
    expect(appearance.idleClip).toBe('Fly Idle');
  });

  it('keeps PNG images outside native model selections and fails closed on missing payloads', () => {
    const staged = rosterFixture();
    expect(resolveRosterPortrait('meshtint-wolf-middle', 'base', 'native', staged)?.url).toMatch(/\.png$/);
    expect(resolveRosterPortrait('meshtint-wolf-middle', 'fire', 'native', staged)).toBeNull();
    expect(resolveRosterAppearance(rosterPet(), 'pet', { ...staged, resolveUrl: () => null })).toBeNull();
    expect(resolveRosterPortrait('meshtint-training-dummy', 'base', 'icon', staged)).toBeNull();
  });

  it('requires the exact typed canonical egg item and retains all 13 native egg actions including held poses', () => {
    const staged = rosterFixture();
    const appearance = resolveRosterEggAppearance(rosterEgg(), staged);
    expect(appearance).toMatchObject({ assetId: 'wolf-egg', defaultAction: 'idle' });
    expect(appearance.motions).toHaveLength(13);
    expect(appearance.motions.find(({ action }) => action === 'underground')).toMatchObject({ clip: 'Underground', loop: true });
    for (const change of [{ slug: 'wolf-egg' }, { pet_species_slug: 'wolf' }, { metadata: { species: 'meshtint-dragon' } }, { item_type: 'food' }]) {
      expect(resolveRosterEggAppearance({ ...rosterEgg(), ...change }, staged)).toBeNull();
    }
  });

  it('only admits its immutable pinned manifest and available files', () => {
    const staged = rosterFixture(), prefix = `../avatar/shared/${staged.pin.directory}/`;
    const manifests = { [`${prefix}manifest.json`]: staged.release };
    const urls = Object.fromEntries(staged.release.files.map((file) => [`${prefix}${file.path}`, staged.resolveUrl(file.path)]));
    const indexes = { [`${prefix}manifest.json`]: '/synthetic/roster.json' };
    expect(stagedRosterRelease(manifests, urls, { releases: [staged.pin] }, indexes)).not.toBeNull();
    expect(stagedRosterRelease(manifests, {}, { releases: [staged.pin] }, indexes)).toBeNull();
    expect(stagedRosterRelease(manifests, urls, { releases: [] }, indexes)).toBeNull();
  });

  it('routes the real appearance adapter to the exact roster without changing Bird bindings', () => {
    const staged = rosterFixture();
    expect(resolveAppearance(rosterPet(), 'pet', undefined, undefined, undefined, staged)?.pipeline).toBe('abby-assets-roster');
    expect(rosterMotions(staged.release, 'wolf-middle', staged.resolveUrl).map(({ id }) => id)).toContain('source-cast-spell');
  });
});
