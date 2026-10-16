import { Group } from 'three';
import { loadAsset, loadAssetPack } from '@abby-assets/avatar-runtime';
import { EGG_CLEARANCE_METERS, PEDESTAL_EGG_ASSETS, PEDESTAL_SUPPORT_ANCHOR } from './pedestal.constants';
export { EGG_CLEARANCE_METERS, PEDESTAL_EGG_ASSETS, PEDESTAL_SUPPORT_ANCHOR } from './pedestal.constants';

const NATIVE_LOOPS = {
  'trunk-pedestal': ['plant-loop', 'PlantLoop'],
  'legendary-egg-idle-breath': ['idle-breath', 'IdleBreath'],
  'legendary-egg-idle-wobble': ['idle-wobble', 'IdleWobble'],
  'legendary-egg-hatching-soon': ['hatching-soon', 'HatchingSoon'],
};

/** Display-only composition. Each take owns its complete native mesh, rig and
 * mixer. HatchingSoon repeats anticipation; it never reports a hatch or reward. */
export function createPedestalPlayback(staged, {
  eggAssetId = 'normal-egg', position = [0, 0, 0], scale = 1, rotationY = 0,
  loadPack = loadAssetPack, load = loadAsset,
  onReady = () => {}, onError = () => {}, invalidate = () => {},
} = {}) {
  const root = new Group();
  root.position.fromArray(position);
  root.scale.setScalar(scale);
  root.rotation.y = rotationY;
  const lifetime = new AbortController();
  const owned = new Set();
  let disposed = false;
  const release = (handle) => {
    if (!owned.delete(handle)) return;
    // The runtime owns and disposes its controllers, skeletons and GPU data.
    handle.instance.dispose();
  };
  const clear = () => { for (const handle of owned) release(handle); root.clear(); };
  const makeHandle = async (pack, assetId) => {
    const instance = await load(pack, { family_id: pack.family_id, asset_id: assetId, variant_id: 'native' },
      { resolveUrl: staged.resolveUrl, signal: lifetime.signal });
    if (disposed || lifetime.signal.aborted) { instance.dispose(); return null; }
    const handle = { instance, controller: null };
    owned.add(handle);
    try {
      const expected = NATIVE_LOOPS[assetId];
      if (expected) {
        const [action, clip] = expected;
        const metadata = instance.variant.animations;
        if (metadata?.actions[action] !== clip || !metadata.clips.some((entry) => entry.name === clip && entry.loop && entry.root_motion === 'source')) {
          throw new Error('The supplied model is missing its native repeating animation.');
        }
        handle.controller = instance.createAnimationController({ rootMotion: 'source' });
        handle.controller.play(action, { loop: true, rootMotion: 'source' });
      }
      return handle;
    } catch (error) { release(handle); throw error; }
  };
  const ready = Promise.resolve().then(async () => {
    if (disposed) return false;
    if (eggAssetId !== null && !PEDESTAL_EGG_ASSETS.includes(eggAssetId)) throw new Error('This egg preview is unavailable.');
    const pack = await loadPack(staged.manifestUrl, { sha256: staged.manifestSha256, signal: lifetime.signal });
    if (disposed) return false;
    const pedestal = await makeHandle(pack, 'trunk-pedestal');
    if (!pedestal) return false;
    const egg = eggAssetId === null ? null : await makeHandle(pack, eggAssetId);
    if (disposed || lifetime.signal.aborted) return false;
    root.add(pedestal.instance.scene);
    if (egg) {
      // Transform the entire runtime wrapper containing both mesh and rig. The
      // exported ground-first pivot is already Y-up in metres: no refitting or
      // second basis correction. The common parent also transforms the anchor.
      const placement = new Group();
      placement.name = 'PedestalEggPlacement';
      placement.position.fromArray(PEDESTAL_SUPPORT_ANCHOR);
      placement.position.y += EGG_CLEARANCE_METERS;
      placement.add(egg.instance.scene);
      root.add(placement);
    }
    onReady();
    invalidate();
    return true;
  }).catch((error) => {
    lifetime.abort();
    clear();
    if (!disposed && error?.name !== 'AbortError') onError(error);
    return false;
  });
  return {
    root, ready,
    update(delta, options) {
      if (disposed) return;
      for (const handle of owned) handle.controller?.update(delta, options);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      lifetime.abort();
      clear();
    },
  };
}
