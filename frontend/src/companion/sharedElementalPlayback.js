import { Group } from 'three';
import { resolveAppearanceTransition, resolveCompanionAppearance } from '@abby-assets/contracts';
import { loadAppearanceTransition, loadAssetPack, loadCompanionAppearance } from '@abby-assets/avatar-runtime';
import { rosterFraming } from './rosterFraming';

const STAGES = ['baby', 'middle', 'grown'];

/** Appearance bindings keep palette identity separate from native motion.
 * Every selected take/transition owns its own parsed rig, materials and mixer. */
export function createSharedElementalPlayback(appearance, {
  loadPack = loadAssetPack, load = loadCompanionAppearance, loadTransition = loadAppearanceTransition,
  onReady = () => {}, onError = () => {}, onPlaybackState = () => {}, invalidate = () => {},
} = {}) {
  const root = new Group(), lifetime = new AbortController(), owned = new Set();
  const bounds = appearance.referenceBounds;
  root.scale.setScalar(appearance.framing === 'bird'
    ? 1.65 / Math.max((bounds?.max[1] ?? 1.65) - (bounds?.min[1] ?? 0), 0.001)
    : rosterFraming(bounds).scale);
  let disposed = false, generation = 0, request, active, idle, readyNotified = false;
  const report = (error, signal) => { if (!disposed && !signal?.aborted && error?.name !== 'AbortError') onError(error); };
  const release = (handle) => {
    if (!owned.delete(handle)) return;
    handle.unsubscribe?.();
    handle.instance.dispose();
  };
  const show = (handle, finished) => {
    if (disposed) return;
    active?.unsubscribe?.(); active?.controller.stop();
    active = handle;
    root.clear(); root.add(handle.instance.scene);
    handle.controller.play(handle.action, { loop: handle.loop, rootMotion: handle.rootMotion });
    if (finished) handle.unsubscribe = handle.controller.onFinished(finished);
    if (!readyNotified) { readyNotified = true; onReady(); }
    onPlaybackState({ status: handle.transition ? 'evolving' : handle === idle ? 'idle' : 'playing',
      variantId: handle.instance.variantId, motion: handle.motion, action: handle.action, stage: appearance.stage });
    invalidate();
  };
  const packReady = loadPack(appearance.manifestUrl, { sha256: appearance.manifestSha256, signal: lifetime.signal });
  const makeHandle = async (query, signal, transition = false) => {
    const pack = await packReady;
    if (disposed || signal.aborted) return null;
    const resolved = (transition ? resolveAppearanceTransition : resolveCompanionAppearance)(pack, query);
    const instance = await (transition ? loadTransition : load)(pack, query, { resolveUrl: appearance.resolveUrl, signal });
    if (disposed || signal.aborted) { instance.dispose(); return null; }
    try {
      const action = resolved.action, clipName = resolved.variant.animations.actions[action];
      const clip = resolved.variant.animations.clips.find((entry) => entry.name === clipName);
      if (!clip || instance.assetId !== resolved.asset.id || instance.variantId !== resolved.variant.id
        || instance.variant.animations?.actions[action] !== clipName || instance.action !== action) {
        throw new Error('Elemental binding does not match its selected native take.');
      }
      const handle = { instance, action, loop: clip.loop, rootMotion: clip.root_motion,
        motion: transition ? null : query.motion, transition,
        controller: instance.createAnimationController({ rootMotion: clip.root_motion }) };
      owned.add(handle); return handle;
    } catch (error) { instance.dispose(); throw error; }
  };
  const ready = makeHandle({ ...appearance.selection, motion: 'idle' }, lifetime.signal).then((handle) => {
    if (!handle) return null;
    idle = handle;
    if (generation === 0) show(idle);
    return idle;
  }).catch((error) => { report(error, lifetime.signal); return null; });
  const current = (token) => !disposed && generation === token;
  const begin = () => {
    generation += 1; request?.abort(); request = new AbortController();
    active?.unsubscribe?.(); active?.controller.stop();
    for (const handle of owned) if (handle !== idle) release(handle);
    active = null;
    if (idle) show(idle);
    onPlaybackState({ status: 'loading', variantId: null, motion: null, action: null, stage: appearance.stage });
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
      const motion = appearance.interactions?.[action] || appearance.motions.find((entry) => entry.id === action || entry.motion === action || entry.action === action);
      if (!motion) return false;
      const { token, signal } = begin();
      try {
        if (!await ready || !current(token)) return false;
        if (motion.motion === 'idle') { restore(token); return true; }
        const handle = await makeHandle({ ...appearance.selection, motion: motion.motion }, signal);
        if (!handle) return false;
        if (!current(token)) { release(handle); return false; }
        show(handle, () => restore(token)); return true;
      } catch (error) { restore(token); report(error, signal); return false; }
    },
    async evolve(from, to) {
      if (disposed || appearance.speciesSlug !== 'chick' || to !== appearance.stage) return false;
      const first = STAGES.indexOf(from), last = STAGES.indexOf(to);
      if (first < 0 || last <= first) return false;
      const { token, signal } = begin(), prepared = [];
      try {
        // The confirmed destination idle is fully loaded before any one-shot.
        // Preload all steps as well so a direct jump never opens a network gap.
        if (!await ready || !current(token)) return false;
        for (let index = first; index < last; index += 1) {
          const handle = await makeHandle({ family_id: appearance.selection.family_id, species_slug: appearance.speciesSlug,
            potion_slug: appearance.potionSlug, from_stage: STAGES[index], to_stage: STAGES[index + 1] }, signal, true);
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
        next(0); return true;
      } catch (error) {
        prepared.forEach(release); restore(token); report(error, signal); return false;
      }
    },
    async reset() { if (!disposed) { const { token } = begin(); if (await ready) restore(token); } },
    update(delta, options) { active?.controller.update(delta, options); },
    dispose() {
      if (disposed) return;
      disposed = true; generation += 1; request?.abort(); lifetime.abort();
      for (const handle of owned) release(handle);
      active = null; root.clear();
    },
  };
}
