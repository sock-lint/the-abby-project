import { Group } from 'three';
import { resolveEvolution } from '@abby-assets/contracts';
import { loadAsset, loadAssetPack } from '@abby-assets/avatar-runtime';
import { BIRD_STAGES } from './sharedBirdRelease';

/** Each variant owns its native rig and resources. Nothing is retargeted or
 * persisted here; an evolution receipt can only present the selected stage. */
export function createSharedBirdPlayback(appearance, {
  loadPack = loadAssetPack, load = loadAsset, onReady = () => {},
  onError = () => {}, onPlaybackState = () => {}, invalidate = () => {},
} = {}) {
  const root = new Group();
  const lifetime = new AbortController();
  const owned = new Set();
  let disposed = false, generation = 0, request, active, idle, readyNotified = false;
  const report = (error, signal) => {
    if (!disposed && !signal?.aborted && error?.name !== 'AbortError') onError(error);
  };
  const release = (handle) => {
    if (!handle || !owned.delete(handle)) return;
    handle.unsubscribe?.();
    handle.instance.dispose();
  };
  const show = (handle, finished) => {
    if (disposed) return;
    active?.unsubscribe?.();
    active?.controller.stop();
    active = handle;
    root.clear();
    root.add(handle.instance.scene);
    handle.controller.play(handle.action, { loop: handle.loop, rootMotion: handle.rootMotion });
    if (finished) handle.unsubscribe = handle.controller.onFinished(finished);
    if (!readyNotified) { readyNotified = true; onReady(); }
    onPlaybackState({ status: handle.action === 'evolve' ? 'evolving' : handle === idle ? 'idle' : 'playing',
      variantId: handle.instance.variantId, stage: appearance.key });
    invalidate();
  };
  const packReady = loadPack(appearance.manifestUrl, { sha256: appearance.manifestSha256, signal: lifetime.signal });
  const makeHandle = async (pack, selection, signal) => {
    const instance = await load(pack, selection, { resolveUrl: appearance.resolveUrl, signal });
    if (disposed || signal.aborted) { instance.dispose(); return null; }
    try {
      const actions = instance.variant.animations.actions;
      const action = Object.keys(actions)[0];
      const metadata = instance.variant.animations.clips.find((entry) => entry.name === actions[action]);
      const handle = {
        instance, controller: instance.createAnimationController({ rootMotion: metadata.root_motion }),
        action, loop: metadata.loop, rootMotion: metadata.root_motion,
      };
      owned.add(handle);
      return handle;
    } catch (error) { instance.dispose(); throw error; }
  };
  const selection = (assetId, variantId) => ({ family_id: appearance.release.family_id, asset_id: assetId, ...(variantId ? { variant_id: variantId } : {}) });
  const ready = packReady.then(async (pack) => {
    const handle = await makeHandle(pack, selection(appearance.key), lifetime.signal);
    if (!handle) return null;
    idle = handle;
    // One static application parent preserves native relative stage sizes and
    // animation pivots. Measuring each moving take would resize the creature.
    const bird = pack.assets.find((asset) => asset.id === 'bird');
    const bounds = bird?.variants.find((variant) => variant.id === bird.default_variant)?.bounds;
    if (bounds) root.scale.setScalar(1.65 / Math.max(bounds.max[1] - bounds.min[1], 0.001));
    if (generation === 0) show(idle);
    return handle;
  }).catch((error) => { report(error, lifetime.signal); return null; });

  const current = (token) => !disposed && token === generation;
  const begin = () => {
    generation += 1;
    request?.abort();
    request = new AbortController();
    active?.unsubscribe?.();
    active?.controller.stop();
    for (const handle of owned) if (handle !== idle) release(handle);
    active = null;
    if (idle) show(idle);
    onPlaybackState({ status: 'loading', variantId: null, stage: appearance.key });
    return { token: generation, signal: request.signal };
  };
  const restore = (token) => {
    if (!current(token) || !idle) return;
    const previous = active;
    show(idle);
    if (previous !== idle) release(previous);
  };

  return {
    root, ready,
    get playing() { return Boolean(active && active !== idle); },
    async play(action) {
      if (disposed) return false;
      const aliased = appearance.interactions?.[action]?.action || action;
      const motion = appearance.motions.find((entry) => entry.id === aliased || entry.action === aliased);
      if (!motion) return false;
      const { token, signal } = begin();
      try {
        if (!await ready || !current(token)) return false;
        if (motion.action === 'idle') { restore(token); return true; }
        const handle = await makeHandle(await packReady, selection(appearance.key, motion.id), signal);
        if (!handle) return false;
        if (!current(token)) { release(handle); return false; }
        show(handle, () => restore(token));
        return true;
      } catch (error) { if (current(token)) restore(token); report(error, signal); return false; }
    },
    async evolve(from, to) {
      if (disposed || to !== appearance.key) return false;
      const first = BIRD_STAGES.indexOf(from), last = BIRD_STAGES.indexOf(to);
      if (first < 0 || last <= first) return false;
      const { token, signal } = begin();
      const prepared = [];
      try {
        if (!await ready || !current(token)) return false;
        const pack = await packReady;
        // Preload every required native transition before presenting it. The
        // destination idle is already owned, so completion has no network gap.
        for (let index = first; index < last; index += 1) {
          const step = resolveEvolution(pack, BIRD_STAGES[index], BIRD_STAGES[index + 1]);
          const handle = await makeHandle(pack, step.selection, signal);
          if (!handle) return false;
          prepared.push(handle);
          if (!current(token)) { prepared.forEach(release); return false; }
        }
        const next = (index) => {
          if (!current(token)) return;
          if (index >= prepared.length) { restore(token); return; }
          show(prepared[index], () => {
            if (!current(token)) return;
            const finished = active;
            next(index + 1);
            if (finished !== active) release(finished);
          });
        };
        next(0);
        return true;
      } catch (error) {
        prepared.forEach(release);
        if (current(token)) restore(token);
        report(error, signal);
        return false;
      }
    },
    async reset() {
      if (disposed) return;
      const { token } = begin();
      if (await ready) restore(token);
    },
    update(delta, options) { active?.controller.update(delta, options); },
    dispose() {
      if (disposed) return;
      disposed = true;
      generation += 1;
      request?.abort();
      lifetime.abort();
      for (const handle of owned) release(handle);
      active = null;
      root.clear();
    },
  };
}
