import { Suspense, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import '../three/console';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Group } from 'three';
import { createCreaturePlayback } from './creaturePlayback';
import { createSharedBirdPlayback } from './sharedBirdPlayback';
import { createSharedRosterPlayback } from './sharedRosterPlayback';
import { createSharedElementalPlayback } from './sharedElementalPlayback';
import { rosterFraming } from './rosterFraming';
import { birdPlaybackIdentity } from './sharedBirdRelease';
import WoodlandScene, { WoodlandCamera } from './WoodlandScene';
import { WOODLAND_BACKGROUND, WOODLAND_CAMERA } from './prepareWoodland';
import useSceneMotionAllowed from './useSceneMotionAllowed';

function Creature({ appearance, greeting, interaction, reaction, animate, motionAllowed, onReady }) {
  const urls = [appearance.url, ...Object.values(appearance.interactions || {}).map((take) => take.url)];
  const gltfs = useLoader(GLTFLoader, urls);
  const invalidate = useThree((state) => state.invalidate);
  const group = useRef();
  const greetingTime = useRef(0);
  const lastInteraction = useRef(null);
  const lastReaction = useRef(null);
  const playback = useMemo(() => createCreaturePlayback(Object.fromEntries(
    gltfs.map((gltf, index) => [index === 0 ? 'idle' : Object.keys(appearance.interactions || {})[index - 1], gltf]),
  ), appearance), [gltfs, appearance]);
  useEffect(() => {
    playback.reset();
    return () => playback.dispose();
  }, [playback]);
  useEffect(() => { onReady(); }, [onReady]);
  useEffect(() => {
    greetingTime.current = greeting && motionAllowed && animate ? 0.8 : 0;
    if ((!motionAllowed || !animate) && group.current) {
      playback.reset();
      group.current.position.y = 0;
      group.current.rotation.y = appearance.rotationY;
    }
    invalidate();
  }, [greeting, motionAllowed, animate, invalidate, appearance.rotationY, playback]);
  useEffect(() => {
    if (!interaction?.id || lastInteraction.current === interaction.id) return;
    lastInteraction.current = interaction.id;
    if (!motionAllowed || !animate) return;
    if (interaction.action === 'hello') greetingTime.current = 0.8;
    else playback.play(interaction.action, invalidate);
    invalidate();
  }, [interaction, motionAllowed, animate, playback, invalidate]);
  useEffect(() => {
    if (!reaction?.id || lastReaction.current === reaction.id) return;
    lastReaction.current = reaction.id;
    if (motionAllowed && animate) {
      greetingTime.current = 1.2;
      invalidate();
    }
  }, [reaction, motionAllowed, animate, invalidate]);
  useFrame((_state, delta) => {
    if (!motionAllowed) return;
    if (animate) playback.update(delta);
    if (greetingTime.current > 0 && group.current) {
      greetingTime.current = Math.max(0, greetingTime.current - Math.min(delta, 0.05));
      group.current.position.y = Math.sin(greetingTime.current * Math.PI * 2.5) * 0.035;
      group.current.rotation.y = appearance.rotationY + Math.sin(greetingTime.current * Math.PI * 2.5) * 0.12;
    }
    if (animate || greetingTime.current > 0) invalidate();
  });
  return <group ref={group} rotation={[0, appearance.rotationY, 0]}>
    <primitive object={playback.root} dispose={null} />
  </group>;
}

function SharedCreature({ appearance, greeting, interaction, reaction, evolution, animate, motionAllowed, onReady, onPlaybackState }) {
  const invalidate = useThree((state) => state.invalidate);
  const root = useMemo(() => new Group(), []);
  const group = useRef(root);
  const playback = useRef(null);
  const greetingTime = useRef(0);
  const lastInteraction = useRef(null);
  const lastEvolution = useRef(null);
  const lastReaction = useRef(null);
  const [error, setError] = useState(null);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const resourceIdentity = birdPlaybackIdentity(appearance);
  const notifyReady = useEffectEvent(() => onReady());
  const notifyPlayback = useEffectEvent((state) => onPlaybackState?.(state));
  const createPlayback = useEffectEvent(() => ({ 'abby-assets-roster': createSharedRosterPlayback, 'abby-assets-elemental': createSharedElementalPlayback }[appearance.pipeline] || createSharedBirdPlayback)(appearance, {
    onReady: () => notifyReady(), onPlaybackState: (state) => notifyPlayback(state), onError: setError, invalidate,
  }));
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const instance = createPlayback();
    playback.current = instance;
    lastEvolution.current = null;
    lastInteraction.current = null;
    lastReaction.current = null;
    root.add(instance.root);
    // Effects own instances so StrictMode's discarded render cannot leak a
    // parsed rig or abort the instance used by the committed scene.
    return () => {
      playback.current = null;
      instance.dispose();
      root.remove(instance.root);
    };
  }, [resourceIdentity, root]);
  useEffect(() => {
    if (!animate || reducedMotion) {
      if (evolution?.id) lastEvolution.current = evolution.id;
      playback.current?.reset();
      return;
    }
    // Visibility initially starts false. Wait for the viewport observer rather
    // than consuming the receipt or freezing an authored source-stage frame.
    if (!motionAllowed) return;
    if (!evolution?.id || lastEvolution.current === evolution.id) return;
    lastEvolution.current = evolution.id;
    playback.current?.evolve(evolution.from, evolution.to);
  }, [evolution, resourceIdentity, animate, motionAllowed, reducedMotion]);
  useEffect(() => {
    if (!interaction?.id || lastInteraction.current === interaction.id) return;
    // An accessible control can sit below the canvas. Keep its request queued
    // until the scene returns to view; explicit motion preferences consume it.
    if (!animate || reducedMotion) {
      lastInteraction.current = interaction.id;
      return;
    }
    if (!motionAllowed) return;
    lastInteraction.current = interaction.id;
    if (interaction.action === 'hello') greetingTime.current = 0.8;
    else playback.current?.play(interaction.action);
    invalidate();
  }, [interaction, resourceIdentity, motionAllowed, animate, reducedMotion, invalidate]);
  useEffect(() => {
    if (!reaction?.id || lastReaction.current === reaction.id) return;
    lastReaction.current = reaction.id;
    if (motionAllowed && animate) greetingTime.current = 1.2;
    invalidate();
  }, [reaction, motionAllowed, animate, invalidate]);
  useEffect(() => {
    greetingTime.current = greeting && motionAllowed && animate ? 0.8 : 0;
    if ((!motionAllowed || !animate) && group.current) {
      group.current.position.y = 0;
      group.current.rotation.y = appearance.rotationY;
    }
    invalidate();
  }, [greeting, motionAllowed, animate, appearance.rotationY, invalidate]);
  useFrame((_state, delta) => {
    if (!motionAllowed || !animate || reducedMotion) return;
    playback.current?.update(delta, { active: motionAllowed, paused: !animate });
    if (greetingTime.current > 0 && group.current) {
      greetingTime.current = Math.max(0, greetingTime.current - Math.min(delta, 0.05));
      group.current.position.y = Math.sin(greetingTime.current * Math.PI * 2.5) * 0.035;
      group.current.rotation.y = appearance.rotationY + Math.sin(greetingTime.current * Math.PI * 2.5) * 0.12;
    }
    invalidate();
  });
  if (error) throw error;
  return <primitive object={root} dispose={null} />;
}

function ContextGuard({ onUnavailable }) {
  const canvas = useThree((state) => state.gl.domElement);
  useEffect(() => {
    const lost = (event) => { event.preventDefault(); onUnavailable(); };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [canvas, onUnavailable]);
  return null;
}

export default function CompanionScene({ appearance, greeting, interaction, reaction, evolution, animate, onReady, onUnavailable, onPlaybackState }) {
  const sceneRef = useRef(null);
  const motionAllowed = useSceneMotionAllowed(sceneRef);
  return (
    <div ref={sceneRef} className="h-full w-full">
      <Canvas frameloop="demand" dpr={[1, 1.5]} camera={WOODLAND_CAMERA} gl={{ antialias: true, alpha: false, powerPreference: 'low-power' }}
      fallback={<span>3D display is unavailable on this device.</span>}>
      <color attach="background" args={[WOODLAND_BACKGROUND]} />
      <WoodlandCamera target={(appearance.pipeline === 'abby-assets-roster' || appearance.framing === 'roster') ? rosterFraming(appearance.referenceBounds).center : undefined} />
      {!appearance.woodland && <ambientLight intensity={2} />}
      <ContextGuard onUnavailable={onUnavailable} />
      <Suspense fallback={null}>
        {appearance.woodland && <WoodlandScene appearance={appearance.woodland} />}
        {['abby-assets-bird', 'abby-assets-roster', 'abby-assets-elemental'].includes(appearance.pipeline)
          ? <SharedCreature appearance={appearance} greeting={greeting} interaction={interaction} reaction={reaction} evolution={evolution} animate={animate} motionAllowed={motionAllowed} onReady={onReady} onPlaybackState={onPlaybackState} />
          : <Creature appearance={appearance} greeting={greeting} interaction={interaction} reaction={reaction} animate={animate} motionAllowed={motionAllowed} onReady={onReady} />}
      </Suspense>
      </Canvas>
    </div>
  );
}
