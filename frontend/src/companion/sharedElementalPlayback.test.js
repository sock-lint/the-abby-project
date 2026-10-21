import { AnimationClip, Group, LoopOnce, LoopRepeat, NumberKeyframeTrack } from 'three';
import { createAnimationController } from '@abby-assets/avatar-runtime';
import { resolveAppearanceTransition, resolveCompanionAppearance } from '@abby-assets/contracts';
import { describe, expect, it, vi } from 'vitest';
import { createSharedElementalPlayback } from './sharedElementalPlayback';
import { resolveElementalAppearance } from './sharedElementalRelease';
import { stagedElementalFixture, syntheticElemental } from '../test/elementalReleaseFixture';

function harness(species = 'chick', potion = 'fire', stage = 'baby') {
  const staged = stagedElementalFixture(['meshtint-dragon', 'meshtint-mushroom'].includes(species));
  const appearance = resolveElementalAppearance(syntheticElemental(species, potion, stage), 'pet', staged);
  const instances = [];
  const makeInstance = (resolved) => {
    const { asset, variant, action } = resolved;
    const scene = new Group(), nativeRoot = new Group();
    scene.name = `Native-${asset.id}-${variant.id}`; nativeRoot.name = 'NativeRoot'; scene.add(nativeRoot);
    const controllers = [];
    const instance = { scene, variant, variantId: variant.id, assetId: asset.id, action,
      createAnimationController: vi.fn((options) => {
        const controller = createAnimationController(nativeRoot, [new AnimationClip(variant.animations.actions[action], 1,
          [new NumberKeyframeTrack('NativeRoot.position[z]', [0, 1], [0, 1])])], { ...options, animations: variant.animations });
        controllers.push(controller); return controller;
      }),
      dispose: vi.fn(() => controllers.forEach((controller) => controller.dispose())),
    };
    instances.push(instance); return instance;
  };
  const load = vi.fn(async (pack, query) => makeInstance(resolveCompanionAppearance(pack, query)));
  const loadTransition = vi.fn(async (pack, query) => makeInstance(resolveAppearanceTransition(pack, query)));
  const loadPack = vi.fn(async () => staged.release), onReady = vi.fn(), onError = vi.fn(), onPlaybackState = vi.fn(), invalidate = vi.fn();
  return { appearance, staged, instances, load, loadTransition, loadPack, onReady, onError, onPlaybackState, invalidate,
    start(overrides = {}) { return createSharedElementalPlayback(appearance, { load, loadTransition, loadPack, onReady, onError, onPlaybackState, invalidate, ...overrides }); } };
}
function finish(playback) { for (let frame = 0; frame < 25; frame += 1) playback.update(0.05); }
const combinations = ['chick', 'meshtint-wolf', 'meshtint-dragon', 'meshtint-mushroom'].flatMap((species) => ['fire', 'ice'].flatMap((potion) => ['baby', 'middle', 'grown'].map((stage) => [species, potion, stage])));

describe('Elemental native playback ownership', () => {
  it.each(combinations)('plays each native %s %s %s take with its declared action, loop and root policy', async (species, potion, stage) => {
    const h = harness(species, potion, stage), playback = h.start();
    await playback.ready;
    const idle = playback.root.children[0], scale = playback.root.scale.x;
    expect(h.loadPack).toHaveBeenCalledWith(h.appearance.manifestUrl, expect.objectContaining({ sha256: h.appearance.manifestSha256, signal: expect.any(AbortSignal) }));
    for (const motion of h.appearance.motions) {
      expect(await playback.play(motion.id)).toBe(true);
      if (motion.motion === 'idle') continue;
      const instance = h.instances.at(-1), controller = instance.createAnimationController.mock.results[0].value;
      expect(instance.scene).toBe(playback.root.children[0]);
      expect(instance.variantId).toBe(motion.variantId);
      expect(instance.createAnimationController).toHaveBeenCalledWith({ rootMotion: motion.rootMotion });
      expect(controller.action.getClip().name).toBe(motion.clip);
      expect(controller.action.loop).toBe(motion.loop ? LoopRepeat : LoopOnce);
      playback.update(0.05);
      expect(instance.scene.children[0].position.z).toBeGreaterThan(0);
      expect(playback.root.scale.x).toBe(scale);
      finish(playback);
      expect(playback.root.children[0]).toBe(motion.loop ? instance.scene : idle);
      await playback.reset();
      expect(playback.root.children[0]).toBe(idle);
      expect(instance.dispose).toHaveBeenCalledOnce();
    }
    expect(h.onReady).toHaveBeenCalledOnce();
    expect(h.onError).not.toHaveBeenCalled();
    expect(h.load.mock.calls.every(([, query]) => query.potion_slug === potion && query.lifecycle_stage === stage)).toBe(true);
    expect(await playback.play('unknown')).toBe(false);
    playback.dispose(); playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
    expect(playback.root.children).toHaveLength(0);
  });

  it.each(['fire', 'ice'].flatMap((potion) => [['baby', 'middle'], ['middle', 'grown'], ['baby', 'grown']].map(([from, to]) => [potion, from, to])))('preloads the destination then presents exact %s Chick %s → %s transitions', async (potion, from, to) => {
    const h = harness('chick', potion, to), playback = h.start();
    expect(await playback.evolve(from, to)).toBe(true);
    expect(h.instances[0].assetId).toBe(`chick-${potion}-${to}`);
    const idle = h.instances[0].scene, transition = h.instances[1];
    expect(playback.root.children[0]).toBe(transition.scene);
    expect(transition.assetId).toBe(`chick-${potion}-${from}-to-${from === 'baby' ? 'middle' : 'grown'}`);
    expect(transition.createAnimationController.mock.results[0].value.action.loop).toBe(LoopOnce);
    expect(h.onPlaybackState).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'evolving', stage: to }));
    finish(playback);
    if (from === 'baby' && to === 'grown') {
      expect(playback.root.children[0]).toBe(h.instances[2].scene);
      expect(h.instances[2].assetId).toBe(`chick-${potion}-middle-to-grown`);
      finish(playback);
    }
    expect(playback.root.children[0]).toBe(idle);
    expect(h.onPlaybackState).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'idle', stage: to, variantId: 'source-idle', motion: 'idle' }));
    expect(playback.playing).toBe(false);
    expect(await playback.evolve(to, from)).toBe(false);
    expect(await playback.evolve('egg', to)).toBe(false);
    playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it.each(['meshtint-wolf', 'meshtint-dragon', 'meshtint-mushroom'])('never invents a %s transition and supports local semantic interaction aliases', async (species) => {
    const h = harness(species, 'ice', species === 'meshtint-wolf' ? 'grown' : 'middle'), playback = h.start();
    await playback.ready;
    expect(await playback.evolve('middle', 'grown')).toBe(false);
    expect(h.loadTransition).not.toHaveBeenCalled();
    expect(await playback.play('play')).toBe(true);
    expect(h.load).toHaveBeenLastCalledWith(h.staged.release, expect.objectContaining({ motion: species === 'meshtint-dragon' ? 'fly-forward-in-place' : 'walk-forward-in-place', potion_slug: 'ice' }), expect.objectContaining({ signal: expect.any(AbortSignal), resolveUrl: h.appearance.resolveUrl }));
    expect(await playback.play('idle')).toBe(true);
    playback.dispose();
  });

  it('cancels slow takes, ignores stale completion, resets to confirmed idle and owns every disposal', async () => {
    const h = harness('chick', 'fire', 'grown');
    let finishLoad;
    const pending = [];
    const playback = h.start({ load: async (...args) => {
      const instance = await h.load(...args);
      if (args[1].motion === 'bite-attack') {
        pending.push({ instance, signal: args[2].signal });
        await new Promise((resolve) => { finishLoad = resolve; });
      }
      return instance;
    } });
    await playback.ready;
    const slow = playback.play('source-bite-attack');
    await vi.waitFor(() => expect(finishLoad).toBeTypeOf('function'));
    expect(await playback.evolve('middle', 'grown')).toBe(true);
    expect(pending[0].signal.aborted).toBe(true);
    finishLoad();
    expect(await slow).toBe(false);
    expect(pending[0].instance.dispose).toHaveBeenCalledOnce();
    const transitionController = h.instances.at(-1).createAnimationController.mock.results[0].value;
    await playback.play('source-fly-forward-in-place');
    const chosen = playback.root.children[0];
    transitionController.mixer.dispatchEvent({ type: 'finished', action: transitionController.action, direction: 1 });
    expect(playback.root.children[0]).toBe(chosen);
    await playback.reset();
    expect(playback.root.children[0]).toBe(h.instances[0].scene);
    playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
    expect(h.onError).not.toHaveBeenCalled();
  });

  it('prevents a half-prepared chain from displaying, disposes prepared resources and preserves target idle on integrity failure', async () => {
    const h = harness('chick', 'ice', 'grown');
    const playback = h.start({ loadTransition: async (...args) => {
      if (args[1].from_stage === 'middle') throw new Error('Transition integrity mismatch');
      return h.loadTransition(...args);
    } });
    expect(await playback.evolve('baby', 'grown')).toBe(false);
    expect(playback.root.children[0]).toBe(h.instances[0].scene);
    expect(h.instances[1].dispose).toHaveBeenCalledOnce();
    expect(h.onPlaybackState.mock.calls.some(([state]) => state.status === 'evolving')).toBe(false);
    expect(h.onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Transition integrity mismatch' }));
    playback.dispose();
    h.instances.forEach((instance) => expect(instance.dispose).toHaveBeenCalledOnce());
  });

  it('disposes a target idle that resolves after unmount and reports invalid manifest/native take loads', async () => {
    const h = harness();
    let finishLoad;
    const playback = h.start({ load: async (...args) => {
      const instance = await h.load(...args);
      await new Promise((resolve) => { finishLoad = resolve; });
      return instance;
    } });
    await vi.waitFor(() => expect(finishLoad).toBeTypeOf('function'));
    playback.dispose(); finishLoad();
    expect(await playback.ready).toBeNull();
    expect(h.onReady).not.toHaveBeenCalled();
    expect(h.instances[0].dispose).toHaveBeenCalledOnce();
    const failed = h.start({ loadPack: async () => { throw new Error('Pinned manifest integrity mismatch'); } });
    expect(await failed.ready).toBeNull();
    expect(h.onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Pinned manifest integrity mismatch' }));
    failed.dispose();
    const invalid = h.start({ load: async (...args) => ({ ...await h.load(...args), action: 'incorrect-action' }) });
    expect(await invalid.ready).toBeNull();
    expect(h.onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Elemental binding does not match its selected native take.' }));
    invalid.dispose();
    expect(h.instances.at(-1).dispose).toHaveBeenCalledOnce();
  });

  it('keeps concurrent Fire/Ice playback resources and cancellation lifetimes independent', async () => {
    const fire = harness('chick', 'fire'), ice = harness('chick', 'ice');
    const left = fire.start(), right = ice.start();
    await Promise.all([left.ready, right.ready]);
    expect(left.root.children[0]).not.toBe(right.root.children[0]);
    expect(fire.instances[0].variant).not.toBe(ice.instances[0].variant);
    await left.play('source-jump-forward-in-place');
    expect(right.playing).toBe(false);
    left.dispose();
    expect(ice.instances[0].dispose).not.toHaveBeenCalled();
    expect(await right.play('source-turn-left')).toBe(true);
    right.dispose();
  });
});
