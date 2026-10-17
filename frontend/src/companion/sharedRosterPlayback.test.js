import { AnimationClip, Group, NumberKeyframeTrack } from 'three';
import { createAnimationController } from '@abby-assets/avatar-runtime';
import { describe, expect, it, vi } from 'vitest';
import { createSharedRosterPlayback } from './sharedRosterPlayback';
import { resolveRosterAppearance, resolveRosterEggAppearance } from './sharedRosterRelease';
import { rosterEgg, rosterFixture, rosterPet } from '../test/rosterReleaseFixture';

function harness(egg = false) {
  const staged = rosterFixture(), instances = [];
  const appearance = egg ? resolveRosterEggAppearance(rosterEgg(), staged) : resolveRosterAppearance(rosterPet(), 'pet', staged);
  const load = vi.fn(async (pack, selection) => {
    const variant = pack.assets.find(({ id }) => id === selection.asset_id).variants.find(({ id }) => id === selection.variant_id);
    const scene = new Group(), model = new Group(); model.name = 'NativeRig'; scene.add(model);
    const clips = variant.animations.clips.map((clip) => new AnimationClip(clip.name, 1, [new NumberKeyframeTrack('NativeRig.position[z]', [0, 1], [0, ['Idle', 'Underground'].includes(clip.name) ? 0 : 1])]));
    const controllers = [];
    const instance = { scene, variant, variantId: variant.id,
      createAnimationController: vi.fn((options) => { const controller = createAnimationController(model, clips, { ...options, animations: variant.animations }); controllers.push(controller); return controller; }),
      dispose: vi.fn(() => controllers.forEach((controller) => controller.dispose())) };
    instances.push(instance); return instance;
  });
  const onError = vi.fn();
  return { appearance, instances, load, onError, start(overrides = {}) { return createSharedRosterPlayback(appearance, { load, loadPack: async () => staged.release, onError, ...overrides }); } };
}

describe('Roster native take lifetime and held poses', () => {
  it('loads only the selected default then owns each requested take independently', async () => {
    const h = harness(), playback = h.start(); await playback.ready;
    expect(h.load).toHaveBeenCalledTimes(1);
    const viewScale = playback.root.scale.clone();
    expect(await playback.play('source-cast-spell')).toBe(true);
    expect(h.load.mock.calls[1][1]).toMatchObject({ asset_id: 'wolf-middle', variant_id: 'source-cast-spell' });
    expect(h.instances[1].createAnimationController).toHaveBeenCalledWith({ rootMotion: 'source' });
    expect(playback.root.scale).toEqual(viewScale);
    await playback.reset();
    expect(h.instances[1].dispose).toHaveBeenCalledOnce();
    playback.dispose(); playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it('aborts a superseded take, disposes a late native rig and cannot overwrite the newest selection', async () => {
    const h = harness(), baseLoad = h.load;
    let releaseLate, delayedSignal;
    const playback = h.start({ load: (pack, selection, options) => selection.variant_id === 'source-cast-spell'
      ? new Promise((resolve) => { delayedSignal = options.signal; releaseLate = async () => resolve(await baseLoad(pack, selection, options)); }) : baseLoad(pack, selection, options) });
    await playback.ready;
    const first = playback.play('source-cast-spell');
    await vi.waitFor(() => expect(releaseLate).toBeTypeOf('function'));
    await playback.play('source-turn-left');
    const newest = playback.root.children[0];
    expect(delayedSignal.aborted).toBe(true);
    await releaseLate(); expect(await first).toBe(false);
    expect(playback.root.children[0]).toBe(newest);
    expect(h.instances.at(-1).dispose).toHaveBeenCalledOnce();
    playback.dispose();
  });

  it('selects held Idle and Underground by action in the single 13-clip egg rig', async () => {
    const h = harness(true), playback = h.start(); await playback.ready;
    expect(h.instances[0].createAnimationController.mock.results[0].value.action.getClip().name).toBe('Idle');
    expect(await playback.play('native:underground')).toBe(true);
    const controller = h.instances.at(-1).createAnimationController.mock.results[0].value;
    expect(controller.action.getClip().name).toBe('Underground');
    playback.update(0.05);
    expect(h.instances.at(-1).scene.children[0].position.z).toBe(0);
    await playback.reset(); expect(playback.playing).toBe(false);
    playback.dispose(); expect(h.onError).not.toHaveBeenCalled();
  });

  it('bounds root-travel egg playback to one clearly labelled take and cancels on unmount', async () => {
    const h = harness(true), motion = h.appearance.motions.find(({ action }) => action === 'roll-forward-w-root');
    expect(motion).toMatchObject({ loop: false, label: expect.stringContaining('(once)') });
    const playback = h.start(); await playback.ready; await playback.play(motion.id);
    playback.dispose();
    expect(await playback.play(motion.id)).toBe(false);
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });
});
