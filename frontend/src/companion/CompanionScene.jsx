import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import { AnimationMixer } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { clone } from 'three/addons/utils/SkeletonUtils.js';
import presentation from '../storybook/presentation.json';
import { prepareModel } from './prepareModel';
import useSceneMotionAllowed from './useSceneMotionAllowed';

function Creature({ appearance, greeting, animate, motionAllowed, onReady }) {
  const gltf = useLoader(GLTFLoader, appearance.url);
  const invalidate = useThree((state) => state.invalidate);
  const group = useRef();
  const greetingTime = useRef(0);
  const model = useMemo(() => prepareModel(gltf.scene), [gltf]);
  const mixer = useMemo(() => new AnimationMixer(model.scene), [model]);
  if (appearance.idleClip && !gltf.animations.some((entry) => entry.name === appearance.idleClip)) {
    throw new Error(`${appearance.url} is missing its verified idle clip.`);
  }
  useEffect(() => {
    const clip = gltf.animations.find((entry) => entry.name === appearance.idleClip);
    if (clip) mixer.clipAction(clip).play();
    return () => { mixer.stopAllAction(); mixer.uncacheRoot(model.scene); };
  }, [appearance.idleClip, gltf, mixer, model]);
  useEffect(() => { onReady(); }, [onReady]);
  useEffect(() => {
    greetingTime.current = greeting && motionAllowed ? 0.8 : 0;
    if (!motionAllowed && group.current) {
      group.current.position.y = 0;
      group.current.rotation.y = appearance.rotationY;
    }
    invalidate();
  }, [greeting, motionAllowed, animate, invalidate, appearance.rotationY]);
  useFrame((_state, delta) => {
    if (!motionAllowed) return;
    if (animate) mixer.update(Math.min(delta, 0.05));
    if (greetingTime.current > 0 && group.current) {
      greetingTime.current = Math.max(0, greetingTime.current - Math.min(delta, 0.05));
      const progress = (0.8 - greetingTime.current) / 0.8;
      group.current.position.y = Math.sin(progress * Math.PI) * 0.16;
      group.current.rotation.y = appearance.rotationY + Math.sin(progress * Math.PI * 2) * 0.15;
    }
    if (animate || greetingTime.current > 0) invalidate();
  });
  return <group ref={group} rotation={[0, appearance.rotationY, 0]}>
    <primitive object={model.scene} position={model.position} scale={model.scale} dispose={null} />
  </group>;
}

function Woodland({ appearance }) {
  const gltf = useLoader(GLTFLoader, appearance.url);
  // Object3D has one parent. Separate transforms for each mounted preview,
  // while retaining the bounded shared geometry/material/texture cache.
  const scene = useMemo(() => clone(gltf.scene), [gltf]);
  return <primitive object={scene} scale={appearance.scale} dispose={null} />;
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

export default function CompanionScene({ appearance, greeting, animate, onReady, onUnavailable }) {
  const sceneRef = useRef(null);
  const motionAllowed = useSceneMotionAllowed(sceneRef);
  return (
    <div ref={sceneRef} className="h-full w-full">
      <Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: [4, 2.8, 5], fov: 35 }} gl={{ antialias: true, alpha: false, powerPreference: 'low-power' }}
      onCreated={({ camera }) => { camera.lookAt(0, 0.85, 0); }}
      fallback={<span>3D display is unavailable on this device.</span>}>
      <color attach="background" args={[presentation.palette.sky]} />
      <ambientLight intensity={1.8} />
      <directionalLight position={[3, 6, 4]} intensity={2.2} />
      <ContextGuard onUnavailable={onUnavailable} />
      <Suspense fallback={null}>
        {appearance.woodland && <Woodland appearance={appearance.woodland} />}
        <Creature appearance={appearance} greeting={greeting} animate={animate} motionAllowed={motionAllowed} onReady={onReady} />
      </Suspense>
      </Canvas>
    </div>
  );
}
