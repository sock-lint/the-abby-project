import { Group } from 'three';
import { loadAsset, loadAssetPack } from '@abby-assets/avatar-runtime';

/** One selected native take owns its complete rig. The roster contains no
 * authored evolution transitions; stage changes select the confirmed idle. */
export function createSharedRosterPlayback(appearance, {
  loadPack = loadAssetPack, load = loadAsset, onReady = () => {}, onError = () => {},
  onPlaybackState = () => {}, invalidate = () => {},
} = {}) {
  const root = new Group(), lifetime = new AbortController(), owned = new Set();
  let disposed = false, generation = 0, request, active, idle;
  const bounds = appearance.referenceBounds;
  if (bounds) root.scale.setScalar(2.8 / Math.max(...bounds.max.map((value, axis) => value - bounds.min[axis]), 0.001));
  const release = (handle) => {
    if (!owned.delete(handle)) return;
    handle.unsubscribe?.();
    handle.instance.dispose();
  };
  const report = (error, signal) => { if (!disposed && !signal?.aborted && error?.name !== 'AbortError') onError(error); };
  const show = (handle, finished) => {
    if (disposed) return;
    active?.unsubscribe?.(); active?.controller.stop();
    active = handle;
    handle.parent.position.set(0, 0, 0);
    root.clear(); root.add(handle.parent);
    handle.controller.play(handle.motion.action, { loop: handle.motion.loop, rootMotion: handle.motion.rootMotion });
    if (finished) handle.unsubscribe = handle.controller.onFinished(finished);
    onPlaybackState({ status: handle === idle ? 'idle' : 'playing', variantId: handle.instance.variantId, action: handle.motion.action, stage: appearance.stage });
    invalidate();
  };
  const packReady = loadPack(appearance.manifestUrl, { sha256: appearance.manifestSha256, signal: lifetime.signal });
  const makeHandle = async (motion, signal) => {
    const pack = await packReady;
    if (disposed || signal.aborted) return null;
    const instance = await load(pack, { family_id: pack.family_id, asset_id: appearance.assetId, variant_id: motion.variantId }, { resolveUrl: appearance.resolveUrl, signal });
    if (disposed || signal.aborted) { instance.dispose(); return null; }
    try {
      if (instance.variant.animations?.actions[motion.action] !== motion.clip) throw new Error('Selected roster motion does not match its native take.');
      const parent = new Group(); parent.add(instance.scene);
      const handle = { instance, parent, motion, controller: instance.createAnimationController({ rootMotion: motion.rootMotion }) };
      owned.add(handle); return handle;
    } catch (error) { instance.dispose(); throw error; }
  };
  const defaultMotion = appearance.motions.find((motion) => motion.variantId === appearance.defaultVariantId && motion.action === appearance.defaultAction);
  const ready = (async () => {
    if (!defaultMotion) throw new Error('Roster default motion is unavailable.');
    idle = await makeHandle(defaultMotion, lifetime.signal);
    if (!idle) return null;
    if (generation === 0) show(idle);
    onReady(); return idle;
  })().catch((error) => { report(error, lifetime.signal); return null; });
  const current = (token) => !disposed && generation === token;
  const begin = () => {
    generation += 1; request?.abort(); request = new AbortController();
    active?.unsubscribe?.(); active?.controller.stop();
    for (const handle of owned) if (handle !== idle) release(handle);
    active = null;
    if (idle) show(idle);
    return { token: generation, signal: request.signal };
  };
  const restore = (token) => {
    if (!current(token) || !idle) return;
    const previous = active;
    show(idle);
    if (previous && previous !== idle) release(previous);
  };
  return {
    root, ready,
    get playing() { return Boolean(active && active !== idle); },
    async play(action) {
      if (disposed) return false;
      const alias = appearance.interactions?.[action];
      const motion = action === 'idle' ? defaultMotion : alias || appearance.motions.find((entry) => entry.id === action || entry.action === action);
      if (!motion) return false;
      const { token, signal } = begin();
      try {
        if (!await ready || !current(token)) return false;
        if (motion === defaultMotion) { restore(token); return true; }
        onPlaybackState({ status: 'loading', variantId: null, stage: appearance.stage });
        const handle = await makeHandle(motion, signal);
        if (!handle) return false;
        if (!current(token)) { release(handle); return false; }
        show(handle, () => restore(token)); return true;
      } catch (error) { restore(token); report(error, signal); return false; }
    },
    // No fabricated animation joins different native rigs or changes ownership.
    async evolve() { return false; },
    async reset() { if (!disposed) { const { token } = begin(); if (await ready) restore(token); } },
    update(delta, options) {
      if (!active) return;
      active.controller.update(delta, options);
    },
    dispose() {
      if (disposed) return;
      disposed = true; generation += 1; request?.abort(); lifetime.abort();
      for (const handle of owned) release(handle);
      active = null; root.clear();
    },
  };
}
