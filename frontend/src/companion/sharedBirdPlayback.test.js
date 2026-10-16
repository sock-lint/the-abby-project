import { AnimationClip, Group, LoopOnce, LoopRepeat, NumberKeyframeTrack } from 'three';
import { createAnimationController } from '@abby-assets/avatar-runtime';
import { describe, expect, it, vi } from 'vitest';
import { createSharedBirdPlayback } from './sharedBirdPlayback';
import { resolveSharedBirdAppearance } from './sharedBirdRelease';
import { stagedBirdFixture, syntheticBird } from '../test/birdReleaseFixture';

function harness(stage = 'chick') {
  const staged = stagedBirdFixture();
  const appearance = resolveSharedBirdAppearance({ ...syntheticBird, evolution_stage: stage, evolved_to_mount: stage === 'bird' }, 'pet', staged);
  const instances = [];
  const load = vi.fn(async (pack, selected) => {
    const asset = pack.assets.find((entry) => entry.id === selected.asset_id);
    const variant = asset.variants.find((entry) => entry.id === (selected.variant_id || asset.default_variant));
    const scene = new Group();
    scene.name = `Native-${asset.id}-${variant.id}`;
    const model = new Group();
    model.name = 'NativeRoot';
    scene.add(model);
    const controllers = [];
    const instance = { scene, variant, variantId: variant.id, assetId: asset.id,
      createAnimationController: vi.fn((options) => {
        const controller = createAnimationController(model, [new AnimationClip(Object.values(variant.animations.actions)[0], 1,
          [new NumberKeyframeTrack('NativeRoot.position[z]', [0, 1], [0, 1])])], { ...options, animations: variant.animations });
        controllers.push(controller);
        return controller;
      }),
      dispose: vi.fn(() => controllers.forEach((controller) => controller.dispose())),
    };
    instances.push(instance);
    return instance;
  });
  const loadPack = vi.fn(async () => staged.release);
  const onReady = vi.fn(), onError = vi.fn(), onPlaybackState = vi.fn();
  return { appearance, instances, load, loadPack, onReady, onError, onPlaybackState,
    start(overrides = {}) { return createSharedBirdPlayback(appearance, { load, loadPack, onReady, onError, onPlaybackState, ...overrides }); } };
}
function finish(playback) { for (let frame = 0; frame < 25; frame += 1) playback.update(0.05); }

describe('Shared bird native playback ownership', () => {
  it.each(['chick', 'fledgling', 'bird'])('plays every %s motion with its declared loop and source travel, then disposes native instances', async (stage) => {
    const h = harness(stage), playback = h.start();
    await playback.ready;
    const idle = playback.root.children[0];
    expect(h.loadPack).toHaveBeenCalledWith('/synthetic/manifest.json', expect.objectContaining({ sha256: 'a'.repeat(64), signal: expect.any(AbortSignal) }));
    for (const motion of h.appearance.motions) {
      expect(await playback.play(motion.id)).toBe(true);
      if (motion.action === 'idle') continue;
      const instance = h.instances.at(-1);
      expect(instance.scene).toBe(playback.root.children[0]);
      expect(instance.createAnimationController).toHaveBeenCalledWith({ rootMotion: 'source' });
      const controller = instance.createAnimationController.mock.results[0].value;
      expect(controller.action.loop).toBe(motion.loop ? LoopRepeat : LoopOnce);
      playback.update(0.05);
      expect(instance.scene.children[0].position.z).toBeGreaterThan(0);
      finish(playback);
      expect(playback.root.children[0]).toBe(motion.loop ? instance.scene : idle);
      expect(instance.dispose).toHaveBeenCalledTimes(motion.loop ? 0 : 1);
      await playback.reset();
      expect(playback.root.children[0]).toBe(idle);
      expect(instance.dispose).toHaveBeenCalledOnce();
    }
    expect(h.onReady).toHaveBeenCalledOnce();
    expect(h.onError).not.toHaveBeenCalled();
    playback.dispose();
    playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it.each([['chick', 'fledgling'], ['fledgling', 'bird'], ['chick', 'bird']])('presents %s → %s with the destination idle preloaded and no progression writes', async (from, to) => {
    const h = harness(to), playback = h.start();
    expect(await playback.evolve(from, to)).toBe(true);
    const idle = h.instances[0].scene;
    expect(h.instances[0].assetId).toBe(to);
    expect(playback.root.children[0].name).toContain(`evolve-${from}-to-`);
    expect(h.instances[1].createAnimationController.mock.results[0].value.action.loop).toBe(LoopOnce);
    finish(playback);
    if (from === 'chick' && to === 'bird') {
      expect(playback.root.children[0].name).toContain('evolve-fledgling-to-bird');
      finish(playback);
    }
    expect(playback.root.children[0]).toBe(idle);
    expect(playback.playing).toBe(false);
    expect(h.onPlaybackState).toHaveBeenLastCalledWith({ status: 'idle', stage: to, variantId: 'source-idle' });
    expect(h.onError).not.toHaveBeenCalled();
    expect(await playback.evolve(to, from)).toBe(false);
    playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it('cancels pending loads, stale completion callbacks, and every instance when replaced or unmounted', async () => {
    const h = harness('bird');
    let resolveLoad;
    const original = h.load;
    const pending = [];
    const load = vi.fn(async (...args) => {
      const instance = await original(...args);
      if (args[1].variant_id === 'source-attack') {
        pending.push({ signal: args[2].signal, instance });
        await new Promise((resolve) => { resolveLoad = resolve; });
      }
      return instance;
    });
    const playback = h.start({ load });
    await playback.ready;
    const idle = playback.root.children[0];
    const slow = playback.play('attack');
    await vi.waitFor(() => expect(resolveLoad).toBeTypeOf('function'));
    expect(await playback.evolve('fledgling', 'bird')).toBe(true);
    expect(pending[0].signal.aborted).toBe(true);
    resolveLoad();
    expect(await slow).toBe(false);
    expect(pending[0].instance.dispose).toHaveBeenCalledOnce();
    const evolution = h.instances.at(-1);
    const controller = evolution.createAnimationController.mock.results[0].value;
    await playback.play('fly');
    const selected = playback.root.children[0];
    controller.mixer.dispatchEvent({ type: 'finished', action: controller.action, direction: 1 });
    expect(playback.root.children[0]).toBe(selected);
    await playback.reset();
    expect(playback.root.children[0]).toBe(idle);
    playback.dispose();
    expect(playback.root.children).toHaveLength(0);
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
    expect(h.onError).not.toHaveBeenCalled();
  });

  it('cleans up an idle that resolves after unmount and reports actual load failures', async () => {
    const h = harness();
    let finishLoad;
    const playback = h.start({ load: async (...args) => {
      const instance = await h.load(...args);
      await new Promise((resolve) => { finishLoad = resolve; });
      return instance;
    } });
    await vi.waitFor(() => expect(finishLoad).toBeTypeOf('function'));
    playback.dispose();
    finishLoad();
    expect(await playback.ready).toBeNull();
    expect(h.onReady).not.toHaveBeenCalled();
    expect(h.instances[0].dispose).toHaveBeenCalledOnce();
    const failed = h.start({ loadPack: async () => { throw new Error('Pinned manifest failed verification'); } });
    expect(await failed.ready).toBeNull();
    expect(h.onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Pinned manifest failed verification' }));
    failed.dispose();
  });

  it('disposes a partially prepared two-step evolution when its second payload fails', async () => {
    const h = harness('bird');
    const playback = h.start({ load: async (...args) => {
      if (args[1].asset_id === 'evolve-fledgling-to-bird') throw new Error('Transition integrity mismatch');
      return h.load(...args);
    } });
    expect(await playback.evolve('chick', 'bird')).toBe(false);
    expect(playback.root.children[0]).toBe(h.instances[0].scene);
    expect(h.instances[1].dispose).toHaveBeenCalledOnce();
    expect(h.onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Transition integrity mismatch' }));
    expect(playback.playing).toBe(false);
    playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });
});
