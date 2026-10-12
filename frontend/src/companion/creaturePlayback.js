import { AnimationMixer, Group, LoopPingPong, LoopRepeat } from 'three';
import { clone } from 'three/addons/utils/SkeletonUtils.js';
import { prepareModel } from './prepareModel';

// Each supplied take retains its own skin/bind pose. Copying its tracks onto
// the idle skeleton distorts the jaw/legs of these particular purchased rigs.
export function createCreaturePlayback(gltfs, appearance) {
  const root = new Group();
  const prepared = prepareModel(gltfs.idle.scene);
  const entries = Object.fromEntries(Object.entries(gltfs).map(([key, gltf]) => {
    const scene = key === 'idle' ? prepared.scene : clone(gltf.scene);
    const wrapper = new Group();
    wrapper.position.fromArray(prepared.position);
    wrapper.scale.setScalar(prepared.scale);
    wrapper.add(scene);
    const mixer = new AnimationMixer(scene);
    const name = key === 'idle' ? appearance.idleClip : appearance.interactions[key]?.clip;
    const clip = gltf.animations.find((entry) => entry.name === name);
    if (name && !clip) throw new Error(`${key === 'idle' ? appearance.url : appearance.interactions[key].url} is missing its verified clip.`);
    return [key, { wrapper, scene, mixer, clip }];
  }));
  let active = entries.idle;
  let onFinished;
  let playing = false;

  function idle() {
    active.mixer.stopAllAction();
    root.clear();
    active = entries.idle;
    root.add(active.wrapper);
    if (active.clip) active.mixer.clipAction(active.clip).reset().play();
    playing = false;
  }
  Object.values(entries).forEach((entry) => entry.mixer.addEventListener('finished', () => {
    if (entry !== active) return;
    const finished = onFinished;
    onFinished = undefined;
    idle();
    finished?.();
  }));
  idle();
  return {
    root,
    get playing() { return playing; },
    play(key, finished) {
      const next = entries[key];
      if (!next?.clip || key === 'idle') return false;
      active.mixer.stopAllAction();
      root.clear();
      active = next;
      root.add(active.wrapper);
      const turning = key === 'left' || key === 'right';
      const action = active.mixer.clipAction(active.clip).reset();
      // The authored turns end facing sideways; reverse the same take to
      // return naturally instead of snapping back to the idle orientation.
      action.setLoop(turning ? LoopPingPong : LoopRepeat, turning ? 2 : 4);
      action.clampWhenFinished = true;
      action.play();
      playing = true;
      onFinished = finished;
      return true;
    },
    update(delta) { active.mixer.update(Math.min(delta, 0.05)); },
    reset() { onFinished = undefined; idle(); },
    dispose() {
      Object.values(entries).forEach(({ mixer, scene }) => {
        mixer.stopAllAction();
        mixer.uncacheRoot(scene);
        // SkeletonUtils creates private skeletons. Their GPU bone textures
        // need disposal even though cached geometry/materials stay shared.
        scene.traverse((node) => node.skeleton?.dispose());
      });
      root.clear();
    },
  };
}
