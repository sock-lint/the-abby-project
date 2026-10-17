import { describe, expect, it, vi } from 'vitest';
import { AnimationClip, Bone, Group, LoopRepeat, Vector3, VectorKeyframeTrack } from 'three';
import { createAnimationController } from '@abby-assets/avatar-runtime';
import { createPedestalPlayback, EGG_CLEARANCE_METERS, PEDESTAL_SUPPORT_ANCHOR } from './pedestalPlayback';

const staged = { release: { family_id: 'meshtint-pedestal-card-ui' }, manifestUrl: '/synthetic-manifest.json', manifestSha256: 'a'.repeat(64), resolveUrl: vi.fn() };
const pack = staged.release;
const clips = {
  'trunk-pedestal': ['plant-loop', 'PlantLoop'],
  'legendary-egg-idle-breath': ['idle-breath', 'IdleBreath'],
  'legendary-egg-idle-wobble': ['idle-wobble', 'IdleWobble'],
  'legendary-egg-hatching-soon': ['hatching-soon', 'HatchingSoon'],
};

function asset(assetId) {
  const scene = new Group(), model = new Group(), bone = new Bone();
  bone.name = 'NativeBone';
  model.add(bone);
  scene.add(model);
  const [action, clip] = clips[assetId] || [];
  const animations = action ? {
    actions: { [action]: clip }, clips: [{ name: clip, loop: true, root_motion: 'source' }], root_node: null,
  } : null;
  const nativeClips = clip ? [new AnimationClip(clip, 1, [new VectorKeyframeTrack('NativeBone.position', [0, .5, 1], [0, 0, 0, .1, .2, 0, 0, 0, 0])])] : [];
  const controllers = [];
  return {
    assetId, scene, model, bone, variant: { animations }, controllers,
    createAnimationController: vi.fn((settings) => {
      const controller = createAnimationController(model, nativeClips, { animations, ...settings });
      vi.spyOn(controller, 'dispose');
      controllers.push(controller);
      return controller;
    }),
    dispose: vi.fn(() => controllers.forEach((controller) => controller.dispose())),
  };
}

function fixture(options = {}) {
  const instances = [];
  const loadPack = vi.fn(async () => pack);
  const load = vi.fn(async (_pack, selection) => {
    const instance = asset(selection.asset_id);
    instances.push(instance);
    return instance;
  });
  const onReady = vi.fn(), onError = vi.fn();
  const playback = createPedestalPlayback(staged, { loadPack, load, onReady, onError, ...options });
  return { instances, loadPack, load, onReady, onError, playback };
}

describe('native pedestal playback', () => {
  it('verifies the pinned manifest and loads only the chosen native mesh and rig pair', async () => {
    const f = fixture();
    expect(await f.playback.ready).toBe(true);
    expect(f.loadPack).toHaveBeenCalledWith(staged.manifestUrl, { sha256: staged.manifestSha256, signal: expect.any(AbortSignal) });
    expect(f.load.mock.calls.map((call) => call[1])).toEqual([
      { family_id: pack.family_id, asset_id: 'trunk-pedestal', variant_id: 'native' },
      { family_id: pack.family_id, asset_id: 'normal-egg', variant_id: 'native' },
    ]);
    expect(f.load.mock.calls[0][2].resolveUrl).toBe(staged.resolveUrl);
    expect(f.playback.root.scale.toArray()).toEqual([1, 1, 1]);
    expect(f.playback.root.children[0]).toBe(f.instances[0].scene);
    const eggPlacement = f.playback.root.getObjectByName('PedestalEggPlacement');
    expect(eggPlacement.position.toArray()).toEqual([0, PEDESTAL_SUPPORT_ANCHOR[1] + EGG_CLEARANCE_METERS, 0]);
    expect(eggPlacement.children[0]).toBe(f.instances[1].scene);
    expect(f.instances[1].model.parent).toBe(f.instances[1].scene);
    expect(f.instances[1].bone.parent).toBe(f.instances[1].model);
    expect(f.instances[1].model.position.toArray()).toEqual([0, 0, 0]);
    expect(f.instances[1].model.scale.toArray()).toEqual([1, 1, 1]);
    expect(f.instances[1].createAnimationController).not.toHaveBeenCalled();
    expect(f.onReady).toHaveBeenCalledOnce();
    f.playback.dispose();
    f.playback.dispose();
    f.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it('transforms the authored common roots and support anchor together', async () => {
    const f = fixture({ position: [3, 4, 5], scale: .5, rotationY: Math.PI / 2 });
    await f.playback.ready;
    f.playback.root.updateMatrixWorld(true);
    expect(f.playback.root.children[0].getWorldScale(new Vector3()).toArray()).toEqual([.5, .5, .5]);
    const point = f.playback.root.getObjectByName('PedestalEggPlacement').getWorldPosition(new Vector3());
    expect(point.toArray()).toEqual([3, 4 + (PEDESTAL_SUPPORT_ANCHOR[1] + EGG_CLEARANCE_METERS) * .5, 5]);
    f.playback.dispose();
  });

  it.each(Object.entries(clips).slice(1))('repeats %s on its own native rig while PlantLoop plays separately', async (eggAssetId, [, clip]) => {
    const f = fixture({ eggAssetId });
    await f.playback.ready;
    expect(f.instances[1].assetId).toBe(eggAssetId);
    expect(f.instances[0].controllers[0].mixer).not.toBe(f.instances[1].controllers[0].mixer);
    for (const instance of f.instances) {
      expect(instance.createAnimationController).toHaveBeenCalledExactlyOnceWith({ rootMotion: 'source' });
      const controller = instance.controllers[0];
      expect(controller.action.loop).toBe(LoopRepeat);
      expect(controller.action.repetitions).toBe(Infinity);
      expect(controller.action.clampWhenFinished).toBe(false);
    }
    expect(f.instances[1].controllers[0].action.getClip().name).toBe(clip);
    const finished = vi.fn();
    f.instances[1].controllers[0].onFinished(finished);
    for (let index = 0; index < 25; index += 1) f.playback.update(.05);
    expect(f.instances[1].controllers[0].time).toBeCloseTo(.25);
    expect(f.instances[1].bone.position.y).toBeGreaterThan(0);
    expect(finished).not.toHaveBeenCalled();
    expect(f.onReady).toHaveBeenCalledOnce();
    f.playback.dispose();
    f.instances.forEach((instance) => expect(instance.controllers[0].dispose).toHaveBeenCalledOnce());
  });

  it('pauses native mixers and caps large resumed frame deltas', async () => {
    const f = fixture({ eggAssetId: 'legendary-egg-idle-wobble' });
    await f.playback.ready;
    const controller = f.instances[1].controllers[0];
    f.playback.update(1, { paused: true });
    f.playback.update(1, { active: false });
    f.playback.update(1, { reducedMotion: true });
    expect(controller.time).toBe(0);
    f.playback.update(8);
    expect(controller.time).toBeCloseTo(.05);
    f.playback.dispose();
    f.playback.update(1);
    expect(controller.action).toBeNull();
  });

  it('can show the pedestal alone without substituting an egg', async () => {
    const f = fixture({ eggAssetId: null });
    await f.playback.ready;
    expect(f.load).toHaveBeenCalledOnce();
    expect(f.playback.root.getObjectByName('PedestalEggPlacement')).toBeUndefined();
    f.playback.dispose();
  });

  it('rejects unsupported identity and incorrect native loop metadata', async () => {
    const unknown = fixture({ eggAssetId: 'owned-pet' });
    expect(await unknown.playback.ready).toBe(false);
    expect(unknown.load).not.toHaveBeenCalled();
    expect(unknown.onError).toHaveBeenCalledOnce();
    const invalid = asset('trunk-pedestal');
    invalid.variant.animations.actions['plant-loop'] = 'other-clip';
    const f = fixture({ load: async () => invalid });
    expect(await f.playback.ready).toBe(false);
    expect(f.onError).toHaveBeenCalledOnce();
    expect(invalid.dispose).toHaveBeenCalledOnce();
    expect(f.playback.root.children).toHaveLength(0);
  });

  it('releases the pedestal when the selected egg fails and keeps retries independent', async () => {
    const pedestal = asset('trunk-pedestal');
    const f = fixture({ load: async (_pack, selection) => {
      if (selection.asset_id === 'trunk-pedestal') return pedestal;
      throw new Error('Synthetic unavailable egg');
    } });
    expect(await f.playback.ready).toBe(false);
    expect(pedestal.dispose).toHaveBeenCalledOnce();
    expect(f.onError).toHaveBeenCalledOnce();
    expect(f.onReady).not.toHaveBeenCalled();
    expect(f.playback.root.children).toHaveLength(0);
    const retry = fixture();
    expect(await retry.playback.ready).toBe(true);
    retry.playback.dispose();
  });

  it('aborts pending manifest and model requests without stale readiness or errors', async () => {
    let resolvePack;
    const f = fixture({ loadPack: () => new Promise((resolve) => { resolvePack = resolve; }) });
    await Promise.resolve();
    f.playback.dispose();
    resolvePack(pack);
    expect(await f.playback.ready).toBe(false);
    expect(f.load).not.toHaveBeenCalled();
    expect(f.onReady).not.toHaveBeenCalled();
    expect(f.onError).not.toHaveBeenCalled();

    let resolveModel, signal;
    const abandoned = asset('trunk-pedestal');
    const g = fixture({ load: (_pack, _selection, options) => new Promise((resolve) => { resolveModel = resolve; signal = options.signal; }) });
    await vi.waitFor(() => expect(resolveModel).toBeTypeOf('function'));
    g.playback.dispose();
    expect(signal.aborted).toBe(true);
    resolveModel(abandoned);
    expect(await g.playback.ready).toBe(false);
    expect(abandoned.dispose).toHaveBeenCalledOnce();
    expect(g.onReady).not.toHaveBeenCalled();
    expect(g.onError).not.toHaveBeenCalled();
  });
});
